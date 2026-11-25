"""P7: the on_step observer in run_agent and the frame recorder built on it (D15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from procedural.agent import make_notifier
from procedural.agent import run_agent as _run_agent
from scripts.frame_recorder import FrameRecorder, basic_world
from scripts.tool_wiring import build_memory, build_sensorimotor, build_tool_registry
from sensorimotor import create_sensorimotor
from tests.procedural.scripted_llm import ScriptedLLM, call, say


def run_agent(*args: Any, **kwargs: Any) -> Any:
    """These tests are about the observer and the frames, not the evidence checklist."""
    kwargs.setdefault("required_evidence", ())
    return _run_agent(*args, **kwargs)


SCENARIO_A = (
    Path(__file__).parents[2] / "sensorimotor" / "scenarios" / "scenario_a.json"
)
QUESTION = "Is your route clear? Then move forward 20 cm."


def _world(clear: bool = False):
    config = json.loads(SCENARIO_A.read_text())
    if clear:
        config["obstacles"] = []
    return create_sensorimotor(config, seed=42)


def _script(
    *tools: tuple[str, dict],
    answer: str = "At first the route looked clear; the recheck found an obstacle, so the move was cancelled and the robot did not move.",
) -> ScriptedLLM:
    replies = [call(name, args, f"c{i}") for i, (name, args) in enumerate(tools, 1)]
    return ScriptedLLM([*replies, say(answer)])


READ = [("query_belief", {"subject": "path_A"}), ("read_lidar", {})]


# ------------------------------------------------------------------ the callback itself
def test_on_step_is_called_after_every_tool_call_in_order() -> None:
    events: list[tuple] = []
    registry, _ = build_tool_registry(sensorimotor=_world())
    run_agent(
        "Is the route clear?",
        _script(*READ, answer="The LiDAR reads 12 cm, blocked."),
        registry,
        on_step=lambda *event: events.append(event),
    )
    assert [e[0] for e in events] == [1, 2]
    assert [e[1] for e in events] == ["query_belief", "read_lidar"]
    assert all(e[4] is False for e in events)
    assert events[1][2] == {} and events[1][3]["ok"] is True


def test_refused_and_invalid_calls_are_reported_too() -> None:
    events: list[tuple] = []
    registry, _ = build_tool_registry(sensorimotor=_world())
    run_agent(
        "q",
        _script(
            ("query_belief", {"subject": "path_A"}),
            ("read_lidar", {"direction": 5}),
            ("read_lidar", {}),
            answer="Blocked at 12 cm.",
        ),
        registry,
        on_step=lambda *event: events.append(event),
    )
    assert [e[3]["ok"] for e in events] == [True, False, True]


def test_the_recheck_read_is_reported_before_the_move_with_auto_true() -> None:
    world = _world(clear=True)
    registry, _ = build_tool_registry(sensorimotor=world)
    seen: list[tuple[str, bool, float]] = []

    def observe(step, tool, args, result, auto):
        seen.append((tool, auto, world.env.pose["x"]))

    run_agent(
        QUESTION,
        _script(
            *READ, ("move_forward", {"distance_cm": 20}), answer="The robot moved."
        ),
        registry,
        on_step=observe,
    )
    assert [(t, a) for t, a, _ in seen] == [
        ("query_belief", False),
        ("read_lidar", False),
        ("read_lidar", True),  # the recheck
        ("move_forward", False),
    ]
    # the recheck saw the robot still at the start; only the move itself changed the pose
    assert [x for _, _, x in seen] == [0, 0, 0, 20]


def test_a_cancelled_move_still_reports_the_recheck_and_the_cancelled_move() -> None:
    events: list[tuple] = []
    registry, _ = build_tool_registry(sensorimotor=_world())
    run_agent(
        QUESTION,
        _script(*READ, ("move_forward", {"distance_cm": 20})),
        registry,
        on_step=lambda *event: events.append(event),
    )
    assert [e[1] for e in events][-2:] == ["read_lidar", "move_forward"]
    assert events[-2][4] is True and events[-1][3]["ok"] is False
    assert events[-1][3]["error"]["code"] == "CONFLICT"


def test_a_failing_observer_never_stops_the_run() -> None:
    def broken(*_: Any) -> None:
        raise RuntimeError("viewer crashed")

    registry, _ = build_tool_registry(sensorimotor=_world())
    out = run_agent(
        "q", _script(*READ, answer="Blocked at 12 cm."), registry, on_step=broken
    )
    assert out.finished and len(out.tool_calls) == 2


def test_the_observer_gets_copies_and_cannot_change_the_log() -> None:
    def vandal(step, tool, args, result, auto):
        result["ok"] = False
        args["tampered"] = True

    registry, _ = build_tool_registry(sensorimotor=_world())
    out = run_agent(
        "q", _script(*READ, answer="Blocked at 12 cm."), registry, on_step=vandal
    )
    assert out.tool_calls[1]["result"]["ok"] is True
    assert "tampered" not in out.tool_calls[1]["args"]


def test_no_callback_is_fine() -> None:
    notify = make_notifier(None)
    notify("read_lidar", {}, {"ok": True}, False)  # nothing happens, nothing raises


# ------------------------------------------------------------------ the frame recorder
def _recorded(clear: bool = False, *tools: tuple[str, dict]):
    memory = build_memory()
    world = _world(clear)
    registry, _ = build_tool_registry(memory=memory, sensorimotor=world)
    recorder = FrameRecorder(world.env, memory)
    recorder.capture_initial()
    run_agent(
        QUESTION,
        _script(
            *(tools or READ),
            answer="At first the route looked clear; the recheck found an obstacle, so the move was cancelled and the robot did not move.",
        ),
        registry,
        on_step=recorder.on_step,
    )
    return recorder


def test_frame_zero_is_taken_before_the_first_call() -> None:
    recorder = _recorded()
    first = recorder.frames[0]
    assert first["step"] == 0 and first["tool"] is None
    assert first["world"]["robot"]["x"] == 0
    assert any(
        b["subject"] == "path_A" for b in first["beliefs"]
    )  # seeded memory is visible


def test_one_frame_per_tool_call_plus_frame_zero() -> None:
    recorder = _recorded()
    assert [f["step"] for f in recorder.frames] == [0, 1, 2]
    assert [f["tool"]["name"] for f in recorder.frames[1:]] == [
        "query_belief",
        "read_lidar",
    ]


def test_a_move_gives_a_recheck_frame_then_a_move_frame() -> None:
    recorder = _recorded(True, *READ, ("move_forward", {"distance_cm": 20}))
    tools = [(f["tool"]["name"], f["tool"]["auto"]) for f in recorder.frames[1:]]
    assert tools[-2:] == [("read_lidar", True), ("move_forward", False)]
    assert recorder.frames[-2]["world"]["robot"]["x"] == 0
    assert recorder.frames[-1]["world"]["robot"]["x"] == 20


def test_frames_have_the_appendix_b_shape_and_survive_json() -> None:
    recorder = _recorded()
    frame = recorder.frames[2]
    assert set(frame) == {"step", "sim_time", "tool", "world", "beliefs"}
    assert set(frame["tool"]) == {"name", "args", "ok", "auto", "result"}
    assert frame["tool"]["result"]["data"]["value"] == 12
    assert {"bounds_cm", "robot", "obstacles", "objects", "lighting", "sensors"} <= set(
        frame["world"]
    )
    assert frame["sim_time"]
    json.dumps(recorder.frames)


def test_sensor_entry_appears_after_the_sensor_is_read() -> None:
    recorder = _recorded()
    assert recorder.frames[1]["world"]["sensors"].get("lidar_front") is None
    reading = recorder.frames[2]["world"]["sensors"]["lidar_front"]
    assert reading["value"] == 12 and reading["status"] == "blocked"


def test_beliefs_in_a_frame_follow_memory_writes() -> None:
    recorder = _recorded(
        False,
        *READ,
        (
            "downgrade_belief",
            {"belief_id": "b_000001", "new_confidence": 0.3, "reason": "r"},
        ),
    )
    before, after = recorder.frames[-2]["beliefs"], recorder.frames[-1]["beliefs"]
    assert len(after) == len(before) + 1  # the lowered copy; nothing was deleted


def test_a_new_recording_starts_clean() -> None:
    recorder = _recorded()
    recorder.capture_initial()
    assert [f["step"] for f in recorder.frames] == [0]


# ------------------------------------------------- recorder details on a stub environment
class StubEnv:
    def __init__(self) -> None:
        self.obstacles = [("wall", 12, -50, 20, 50)]

    def get_state(self) -> dict:
        return {
            "robot": {"x": 0.0, "y": 0.0, "heading_deg": 0.0},
            "time": "2026-11-23T00:00:00Z",
            "lighting": {"name": "white", "color_shift": {}},
            "objects": [{"object_id": "box_01", "x": 300, "y": 0, "true_color": "red"}],
            "obstacles": [
                {"obstacle_id": n, "x_min": a, "y_min": b, "x_max": c, "y_max": d}
                for n, a, b, c, d in self.obstacles
            ],
        }


class StubMemory:
    def snapshot(self) -> dict:
        return {"nodes": [{"belief_id": "b_000001"}], "edges": []}


def test_an_obstacle_that_appears_mid_run_is_marked_with_its_step() -> None:
    env = StubEnv()
    recorder = FrameRecorder(env, StubMemory(), export_frame=None)
    recorder._export = None
    recorder.capture_initial()
    env.obstacles.append(("cart_01", 140, -30, 170, 30))
    recorder.on_step(3, "read_lidar", {}, {"ok": True, "data": None}, False)
    added = {
        o["id"]: o["added_at_step"] for o in recorder.frames[-1]["world"]["obstacles"]
    }
    assert added == {"wall": None, "cart_01": 3}


def test_bounds_cover_the_robot_the_obstacles_and_the_objects() -> None:
    world = basic_world(StubEnv(), {"wall"}, 0)
    box = world["bounds_cm"]
    assert box["x_min"] <= 0 and box["x_max"] >= 300 and box["y_min"] <= -50


def test_an_injected_export_function_is_used_and_its_world_key_is_understood() -> None:
    def export(env):
        return {"sim_time": "T", "world": {"robot": {"x": 9}, "sensors": {}}}

    recorder = FrameRecorder(StubEnv(), StubMemory(), export_frame=export)
    recorder.capture_initial()
    assert recorder.frames[0]["sim_time"] == "T"
    assert recorder.frames[0]["world"]["robot"] == {"x": 9}


def test_an_export_that_returns_only_the_world_is_accepted_too() -> None:
    recorder = FrameRecorder(
        StubEnv(), StubMemory(), export_frame=lambda env: {"robot": {"x": 1}}
    )
    recorder.capture_initial()
    assert recorder.frames[0]["world"]["robot"] == {"x": 1}


def test_a_failing_export_skips_the_frame_instead_of_raising() -> None:
    def broken(env):
        raise ValueError("bad frame")

    recorder = FrameRecorder(StubEnv(), StubMemory(), export_frame=broken)
    recorder.capture_initial()
    recorder.on_step(1, "read_lidar", {}, {"ok": True}, False)
    assert recorder.frames == []


def test_build_memory_and_world_helpers_still_give_a_working_pair() -> None:
    memory, world = build_memory(), build_sensorimotor("scenario_a")
    recorder = FrameRecorder(world.env, memory)
    recorder.capture_initial()
    assert len(recorder.frames) == 1
