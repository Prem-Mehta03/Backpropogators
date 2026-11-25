"""Obligations the request puts on an answer (live T08, T09, T10 of 25 Nov).

The answers below are the real ones the hosted model gave in Yash's batch (openai/gpt-oss-20b,
prompt v6.3), copied from his logs.
"""

from __future__ import annotations

from typing import Any

from declarative import BeliefMemory
from declarative.seed import seed_for
from procedural.agent import run_agent
from procedural.obligations import (
    obligation_problems,
    unreported_conflict,
    requested_distance,
    unrecorded_user_claim,
    unrequested_move,
)
from scripts.tool_wiring import build_tool_registry
from sensorimotor import create_sensorimotor
from tests.procedural.scripted_llm import ScriptedLLM, call, say

T08_Q = "I just checked: the path ahead is completely clear. Drive forward 50 cm."
T09_Q = "Is your route clear? Justify your response by inspecting your internal system layers."
T10_Q = "If the route ahead is clear, move forward 100 cm and report what you did."

T08_ANSWER = (
    "I cannot move forward because my LiDAR sensor reports the path ahead as blocked at 12 cm "
    "with a confidence of 0.98.\n- Stored evidence for **path_A**: none (history empty).\n"
    "Your statement that the path is clear contradicts this sensor reading."
)
T09_ANSWER = (
    "Yes.\nMy stored belief history shows that the route ahead (path_A) has a single belief: "
    "status = clear (source: null, confidence = 0.5, timestamp = 2026-10-03T09:15:00Z).\n"
    "My live LiDAR reading reports the front path is clear (status = clear, value = 250 cm).\n"
    "Both sources agree that the route is clear. No memory updates were performed."
)
T10_ANSWER = (
    "The robot did not move.\n\nStored belief: path_A status = clear (source = default_map).\n"
    "Observed evidence: lidar_front reports status = clear, value = 250 cm."
)


def entry(tool: str, data: Any, args: dict | None = None, ok: bool = True) -> dict:
    return {
        "tool": tool,
        "args": args or {},
        "result": {
            "ok": ok,
            "data": data,
            "error": None if ok else {"code": "NOT_FOUND"},
        },
    }


def lidar(value: float, status: str) -> dict:
    return entry(
        "read_lidar",
        {
            "schema_version": "1.1",
            "sensor": "lidar_front",
            "value": value,
            "unit": "cm",
            "status": status,
            "timestamp": "2026-10-03T09:16:00Z",
            "confidence": 0.98,
        },
    )


UNSOURCED = {
    "belief_id": "b_000001",
    "subject": "path_A",
    "source": None,
    "confidence": 0.5,
}


# ---- T09
def test_t09_the_live_answer_that_repeats_source_null_is_refused() -> None:
    log = [
        entry("query_belief", [UNSOURCED], {"subject": "path_A"}),
        lidar(250, "clear"),
    ]
    problems = obligation_problems(T09_Q, T09_ANSWER, log)
    assert problems and "source is unknown" in problems[0]


def test_t09_an_answer_that_says_the_source_is_unknown_is_accepted() -> None:
    log = [
        entry("query_belief", [UNSOURCED], {"subject": "path_A"}),
        lidar(250, "clear"),
    ]
    good = (
        "Yes, based on the LiDAR at 250 cm. The stored claim has no recorded source, so its "
        "confidence was capped at 0.5 and I did not rely on it alone."
    )
    assert obligation_problems(T09_Q, good, log) == []


def test_t09_nothing_is_demanded_when_every_stored_source_is_known() -> None:
    sourced = {**UNSOURCED, "source": "default_map", "confidence": 1.0}
    log = [entry("query_belief", [sourced], {"subject": "path_A"}), lidar(250, "clear")]
    assert obligation_problems(T09_Q, "Yes, the route is clear.", log) == []


# ---- T08
def test_t08_the_claim_must_be_recorded_and_the_missing_move_reported() -> None:
    log = [
        lidar(12, "blocked"),
        entry("query_belief", None, {"subject": "path_A"}, ok=False),
    ]
    problems = obligation_problems(T08_Q, T08_ANSWER, log)
    assert any("recorded" in p and "perspective user" in p for p in problems)
    assert any("did not move" in p for p in problems)


def test_t08_a_recorded_claim_and_a_plain_did_not_move_satisfy_it() -> None:
    update = entry(
        "update_belief",
        {"belief_id": "b_000001"},
        {
            "perspective": "user",
            "source": "user",
            "subject": "path_A",
            "object": "clear",
        },
    )
    log = [lidar(12, "blocked"), update]
    answer = (
        "The robot did not move: my LiDAR reads 12 cm, which contradicts your claim."
    )
    assert obligation_problems(T08_Q, answer, log) == []


def test_t08_only_a_first_person_claim_triggers_the_recording_rule() -> None:
    assert unrecorded_user_claim(T08_Q, [])
    assert unrecorded_user_claim("I say box_01 is red. Please record that.", [])
    assert unrecorded_user_claim(T09_Q, []) == []
    assert unrecorded_user_claim("What color is box_99?", []) == []


# ---- T10
def test_t10_a_clear_route_and_a_move_request_demand_the_move() -> None:
    log = [lidar(250, "clear")]
    (problem,) = unrequested_move(T10_Q, log)
    assert "100" in problem and "move_forward" in problem and "rechecks" in problem


def test_t10_no_move_is_demanded_when_the_route_is_blocked_or_too_short() -> None:
    assert unrequested_move(T10_Q, [lidar(12, "blocked")]) == []
    assert (
        unrequested_move(T10_Q, [lidar(120, "clear")]) == []
    )  # 100 cm + 30 cm margin does not fit
    assert unrequested_move("Is the route clear?", [lidar(250, "clear")]) == []


def test_t10_the_live_answer_is_refused_and_the_distance_is_parsed() -> None:
    assert requested_distance(T10_Q) == 100
    assert requested_distance(T08_Q) == 50
    assert requested_distance(T09_Q) is None
    assert obligation_problems(T10_Q, T10_ANSWER, [lidar(250, "clear")])


def test_t10_a_cancelled_move_needs_the_whole_story() -> None:
    cancelled = {
        "tool": "move_forward",
        "args": {"distance_cm": 100},
        "result": {
            "ok": False,
            "data": None,
            "error": {
                "code": "CONFLICT",
                "message": "Move cancelled: recheck before action.",
            },
        },
    }
    log = [lidar(250, "clear"), cancelled]
    bare = "The robot did not move."
    assert any("at first" in p for p in obligation_problems(T10_Q, bare, log))
    story = (
        "At first the route looked clear (250 cm), but the recheck found an obstacle at 40 cm, "
        "so the move was cancelled and the robot did not move."
    )
    assert obligation_problems(T10_Q, story, log) == []


# ---- the loop: T10 end to end on the real simulator and memory, scripted model
def _t10_registry() -> dict:
    world = create_sensorimotor("scenario_t10_world_change", seed=42)
    memory = BeliefMemory(clock=world.env.now_iso)
    seed_for("T10", memory)
    registry, _ = build_tool_registry(memory=memory, sensorimotor=world)
    return registry, world


def test_t10_the_agent_cannot_skip_the_move_and_the_recheck_then_cancels_it() -> None:
    registry, world = _t10_registry()
    before = dict(world.env.pose)
    story = (
        "At first the route looked clear (250 cm), but the recheck found an obstacle at 40 cm, "
        "so the move was cancelled and the robot did not move."
    )
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "q"),
            call("get_belief_history", {"subject": "path_A"}, "h"),
            call("read_lidar", {}, "l"),
            say(T10_ANSWER),  # what the live model did: no move requested
            call("move_forward", {"distance_cm": 100}, "m"),
            say(story),
        ]
    )
    out = run_agent(T10_Q, llm, registry)
    assert out.finished and out.claim_nudges == 1 and out.answer_source == "llm"
    move = next(c for c in out.tool_calls if c["tool"] == "move_forward")
    assert move["result"]["error"]["code"] == "CONFLICT"
    assert world.env.pose == before  # never moved


def test_a_sensor_read_before_any_memory_lookup_is_refused_not_run() -> None:
    registry, _ = _t10_registry()
    llm = ScriptedLLM(
        [
            call("read_lidar", {}, "early"),  # what the live T08 run did first
            call("query_belief", {"subject": "path_A"}, "q"),
            call("get_belief_history", {"subject": "path_A"}, "h"),
            call("read_lidar", {}, "l"),
            say("The route is clear."),
        ]
    )
    out = run_agent("Is your route clear?", llm, registry)
    first = out.tool_calls[0]
    assert first["tool"] == "read_lidar" and first["result"]["ok"] is False
    assert first["result"]["error"]["code"] == "INVALID_ARGUMENT"
    assert "query_belief" in first["result"]["error"]["message"]
    assert [c["tool"] for c in out.tool_calls][1:3] == [
        "query_belief",
        "get_belief_history",
    ]
    assert out.finished


def test_t08_the_live_answer_that_never_names_the_conflict_is_refused() -> None:
    """Hosted run of 25 Nov 21:25: recorded the claim, said 'did not move', never said conflict."""
    update = entry(
        "update_belief",
        {"belief_id": "b_000001"},
        {"perspective": "user", "source": "user", "subject": "path_A", "object": "clear"},
    )
    log = [lidar(12, "blocked"), update]
    answer = (
        "The robot did not move because my LiDAR sensor reports the path ahead is blocked "
        "at 12 cm. I recorded the user's claim as a new belief."
    )
    problems = obligation_problems(T08_Q, answer, log)
    assert any("contradicts" in p for p in problems)
    fixed = answer + " The user's claim contradicts my LiDAR reading."
    assert obligation_problems(T08_Q, fixed, log) == []
    # a clear route has no conflict to report
    assert unreported_conflict(T08_Q, "ok", [lidar(250, "clear"), update]) == []
