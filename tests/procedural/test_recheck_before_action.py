"""P6: recheck before action (D11) and disclosure of cancelled moves and half-done writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from procedural.agent import run_agent
from procedural.claims import (
    cancelled_moves,
    failed_writes,
    unbacked_write_claims,
    undisclosed_actions,
)
from procedural.fallback_summary import build_fallback_summary
from procedural.prompts import build_claim_note
from procedural.recheck import RECHECK_MARGIN_CM, recheck_before_action
from procedural.update_guard import check_memory_call
from scripts.tool_wiring import build_tool_registry
from sensorimotor import create_sensorimotor
from tests.procedural.scripted_llm import ScriptedLLM, call, say
from tests.procedural.test_checklist_enforcement import entry

SCENARIO_A = (
    Path(__file__).parents[2] / "sensorimotor" / "scenarios" / "scenario_a.json"
)
QUESTION = "Is your route clear? Then move forward 20 cm."


def lidar_envelope(
    value: float, status: str = "clear", sensor: str = "lidar_front"
) -> dict:
    return {
        "ok": True,
        "tool": "read_lidar",
        "data": {
            "sensor": sensor,
            "value": value,
            "unit": "cm",
            "status": status,
            "timestamp": "2026-11-23T00:00:00Z",
            "confidence": 0.98,
            "schema_version": "1.0",
        },
        "error": None,
        "timestamp": "2026-11-23T00:00:00Z",
        "schema_version": "1.0",
    }


def fake_registry(envelope: dict, seen: list | None = None) -> dict[str, Any]:
    def read_lidar(direction: str = "front") -> dict:
        if seen is not None:
            seen.append(direction)
        return envelope

    return {"read_lidar": read_lidar}


# ---------------------------------------------------------------- the rule itself
def test_margin_is_thirty_centimetres() -> None:
    assert RECHECK_MARGIN_CM == 30


def test_clear_path_with_room_to_spare_lets_the_move_run() -> None:
    check = recheck_before_action(
        "move_forward", {"distance_cm": 20}, fake_registry(lidar_envelope(200))
    )
    assert check is not None and check.cancel is None
    assert check.details["passed"] is True and check.details["required_cm"] == 50


def test_a_blocked_ultrasonic_read_cancels_clear_lidar_and_notifies_both() -> None:
    registry = fake_registry(lidar_envelope(250))
    registry["read_ultrasonic"] = lambda: {
        **lidar_envelope(15, "blocked", "ultrasonic_front"),
        "tool": "read_ultrasonic",
    }
    events = []
    out = run_agent(
        "Move forward 20 cm",
        ScriptedLLM(
            [
                call("move_forward", {"distance_cm": 20}, "move"),
                say(
                    "The move was cancelled and the robot did not move. The LiDAR and the "
                    "ultrasonic sensor disagree, so a recheck is needed before moving."
                ),
            ]
        ),
        registry,
        required_evidence=(),
        on_step=lambda *event: events.append(event),
    )
    assert [(name, auto) for _, name, _, _, auto in events] == [
        ("read_lidar", True),
        ("read_ultrasonic", True),
        ("move_forward", False),
    ]
    (move,) = out.tool_calls
    assert move["result"]["error"]["code"] == "CONFLICT"
    assert "ultrasonic" in move["result"]["error"]["message"]
    assert [read["result"] for read in move["guard"]["recheck"]["reads"]] == [
        events[0][3],
        events[1][3],
    ]


def test_blocked_status_cancels_even_if_the_reported_distance_is_large() -> None:
    check = recheck_before_action(
        "move_forward",
        {"distance_cm": 20},
        fake_registry(lidar_envelope(250, "blocked")),
    )
    assert check is not None and check.cancel is not None


def test_malformed_move_is_rejected_before_any_recheck() -> None:
    events: list[str] = []
    out = run_agent(
        "Move forward",
        ScriptedLLM(
            [
                call("move_forward", {"distance_cm": 20, "unknown": True}),
                say("Refused."),
            ]
        ),
        fake_registry(lidar_envelope(250), events),
        required_evidence=(),
    )
    assert not events
    assert out.tool_calls[0]["result"]["error"]["code"] == "INVALID_ARGUMENT"


def test_reading_exactly_distance_plus_margin_is_allowed_one_less_is_not() -> None:
    ok = recheck_before_action(
        "move_forward", {"distance_cm": 20}, fake_registry(lidar_envelope(50))
    )
    no = recheck_before_action(
        "move_forward", {"distance_cm": 20}, fake_registry(lidar_envelope(49))
    )
    assert ok.cancel is None and no.cancel is not None


def test_cancel_message_names_the_reading_and_says_the_robot_did_not_move() -> None:
    check = recheck_before_action(
        "move_forward",
        {"distance_cm": 20},
        fake_registry(lidar_envelope(12, "blocked")),
    )
    assert "recheck before action" in check.cancel and "12" in check.cancel
    assert "did not move" in check.cancel and "50" in check.cancel


def test_backward_moves_read_the_rear_lidar() -> None:
    seen: list[str] = []
    recheck_before_action(
        "move_backward", {"distance_cm": 10}, fake_registry(lidar_envelope(300), seen)
    )
    assert seen == ["back"]


def test_other_tools_and_malformed_distances_are_not_rechecked() -> None:
    registry = fake_registry(lidar_envelope(300))
    assert recheck_before_action("turn", {"degrees": 90}, registry) is None
    assert recheck_before_action("read_lidar", {}, registry) is None
    assert recheck_before_action("move_forward", {}, registry) is None
    assert (
        recheck_before_action("move_forward", {"distance_cm": "far"}, registry) is None
    )
    assert recheck_before_action("move_forward", {"distance_cm": -5}, registry) is None
    assert (
        recheck_before_action("move_forward", {"distance_cm": True}, registry) is None
    )


def test_an_unreadable_lidar_cancels_the_move() -> None:
    failed = {
        "ok": False,
        "tool": "read_lidar",
        "data": None,
        "error": {
            "code": "SENSOR_UNAVAILABLE",
            "message": "LiDAR off",
            "retryable": True,
        },
        "timestamp": "2026-11-23T00:00:00Z",
        "schema_version": "1.0",
    }
    check = recheck_before_action(
        "move_forward", {"distance_cm": 5}, fake_registry(failed)
    )
    assert check.cancel and "could not be read" in check.cancel
    assert "did not move" in check.cancel


def test_an_unusable_reading_cancels_the_move() -> None:
    check = recheck_before_action(
        "move_forward",
        {"distance_cm": 5},
        fake_registry(lidar_envelope(100, "unknown")),
    )
    assert check.cancel and "unusable" in check.cancel


def test_a_registry_without_lidar_cancels_the_move() -> None:
    check = recheck_before_action("move_forward", {"distance_cm": 5}, {})
    assert check is not None and check.cancel is not None


# ---------------------------------------------------- inside the loop, on the real world
def _real(world_edit=None):
    config = json.loads(SCENARIO_A.read_text())
    if world_edit:
        world_edit(config)
    world = create_sensorimotor(config, seed=42)
    registry, _ = build_tool_registry(sensorimotor=world)
    return registry, world


def _script(answer: str) -> ScriptedLLM:
    return ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call("move_forward", {"distance_cm": 20}, "c3"),
            say(answer),
        ]
    )


def test_blocked_path_move_is_cancelled_and_the_robot_stays_put() -> None:
    registry, world = _real()
    before = world.env.pose
    out = run_agent(
        QUESTION, _script("The move was cancelled; the robot did not move."), registry
    )
    move = out.tool_calls[3]
    assert move["tool"] == "move_forward" and move["result"]["ok"] is False
    assert move["result"]["error"]["code"] == "CONFLICT"
    assert "recheck before action" in move["result"]["error"]["message"]
    assert move["guard"]["recheck"]["passed"] is False
    assert move["guard"]["recheck"]["reading_cm"] == 12
    assert world.env.pose == before and out.finished


def test_the_log_stays_one_entry_per_model_request() -> None:
    registry, _ = _real()
    out = run_agent(QUESTION, _script("The move was cancelled."), registry)
    assert [c["tool"] for c in out.tool_calls] == [
        "query_belief",
        "get_belief_history",
        "read_lidar",
        "move_forward",
    ]


def test_clear_path_move_runs_and_the_recheck_is_logged() -> None:
    def clear(config: dict) -> None:
        config["obstacles"] = []

    registry, world = _real(clear)
    out = run_agent(
        QUESTION, _script("The path was clear and the robot moved."), registry
    )
    move = out.tool_calls[3]
    assert move["result"]["ok"] is True and world.env.pose["x"] == 20
    assert move["guard"]["recheck"]["passed"] is True
    assert move["guard"]["recheck"]["reading_cm"] == 400


def test_the_model_cannot_skip_the_recheck_by_asking_again() -> None:
    registry, world = _real()
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call("move_forward", {"distance_cm": 20}, "c3"),
            call("move_forward", {"distance_cm": 5}, "c4"),
            say("Both moves were cancelled; the robot did not move."),
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    assert [c["result"]["ok"] for c in out.tool_calls[3:]] == [False, False]
    assert world.env.pose["x"] == 0


def test_an_answer_that_hides_a_cancelled_move_is_refused_then_accepted() -> None:
    registry, _ = _real()
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call("move_forward", {"distance_cm": 20}, "c3"),
            say("Route checked. The LiDAR reads 12 cm."),
            say(
                "The LiDAR reads 12 cm, so the move was cancelled and the robot did not move."
            ),
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    assert out.claim_nudges == 1 and out.finished
    assert "cancelled" in out.answer
    assert (
        "cancelled by the recheck before action" in out.claim_refusals[0]["problems"][0]
    )


def test_a_model_that_never_discloses_ends_in_a_fallback_that_does() -> None:
    registry, _ = _real()
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call("move_forward", {"distance_cm": 20}, "c3"),
            *[say("Route checked.")] * 6,
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    assert out.answer_source == "fallback_summary"
    assert "Moves in this run:" in out.answer and "cancelled" in out.answer
    assert unbacked_write_claims(out.answer, out.tool_calls, True) == []


# ------------------------------------------------- disclosure of half-done memory changes
OK = {
    "belief_id": "b_000004",
    "subject": "path_A",
    "predicate": "status",
    "object": "clear",
}


def _writes(downgrade_ok: bool, update_ok: bool) -> list[dict]:
    log = []
    for tool, ok in (("downgrade_belief", downgrade_ok), ("update_belief", update_ok)):
        log.append(
            entry(tool, ok=ok, code=None if ok else "CONFLICT", data=OK if ok else None)
        )
    return log


def test_failed_writes_lists_only_a_half_done_change() -> None:
    assert failed_writes(_writes(True, False)) == ["update_belief"]
    assert failed_writes(_writes(False, True)) == ["downgrade_belief"]
    assert failed_writes(_writes(True, True)) == []
    assert (
        failed_writes(_writes(False, False)) == []
    )  # nothing changed, nothing half-done
    assert failed_writes([]) == []


def test_a_failed_write_that_was_retried_successfully_is_not_half_done() -> None:
    log = [*_writes(True, False), entry("update_belief", data=OK)]
    assert failed_writes(log) == []


def test_half_done_change_must_be_disclosed() -> None:
    log = _writes(True, False)
    silent = "The route is blocked. I downgraded b_000004."
    assert undisclosed_actions(silent, log)
    said = "I downgraded b_000004, but recording the new reading failed, so memory is half updated."
    assert undisclosed_actions(said, log) == []


def test_the_failure_must_be_about_the_write_that_failed() -> None:
    log = _writes(False, True)  # the downgrade failed
    wrong = "I updated memory, but the camera read failed."
    assert undisclosed_actions(wrong, log)
    right = "The update went through, but the downgrade was refused."
    assert undisclosed_actions(right, log) == []


def test_cancelled_moves_are_found_by_the_recheck_phrase_only() -> None:
    cancelled = entry("move_forward", ok=False, code="CONFLICT")
    cancelled["result"]["error"]["message"] = "Move cancelled: recheck before action."
    other = entry("move_forward", ok=False, code="INVALID_ARGUMENT")
    assert cancelled_moves([cancelled, other]) == [cancelled]


def test_a_cancelled_move_cannot_be_reported_as_movement() -> None:
    cancelled = entry("move_forward", ok=False, code="CONFLICT")
    cancelled["result"]["error"]["message"] = "Move cancelled: recheck before action."
    problems = undisclosed_actions(
        "The move was cancelled. I moved anyway.", [cancelled]
    )
    assert problems and "no move tool succeeded" in problems[0]


def test_disclosure_problems_get_their_own_note_without_the_make_the_call_advice() -> (
    None
):
    note = build_claim_note(
        ["say that the move was cancelled by the recheck before action"]
    )
    assert "Add what is missing" in note and "make the missing tool call" not in note
    mixed = build_claim_note(
        ["you claim a downgrade, but no downgrade_belief call succeeded", "say that x"]
    )
    assert "make the missing tool call" in mixed


# ------------------------------------------------- the guard ignores the rear LiDAR
def test_a_rear_lidar_read_does_not_look_like_a_sensor_disagreement() -> None:
    belief = {
        "belief_id": "b_000001",
        "subject": "path_A",
        "predicate": "status",
        "object": "clear",
        "confidence": 1.0,
        "perspective": "historical",
    }
    front = lidar_envelope(12, "blocked")["data"]
    rear = lidar_envelope(300, "clear", "lidar_back")["data"]
    log = [
        entry("query_belief", data=[belief]),
        entry("read_lidar", data=front),
        entry("read_lidar", data=rear),
    ]
    args = {"belief_id": "b_000001", "new_confidence": 0.3, "reason": "r"}
    assert check_memory_call("downgrade_belief", args, log).error is None


def test_fallback_summary_lists_a_move_that_ran() -> None:
    log = [entry("move_forward", data={"sensor": "position"})]
    log[0]["args"] = {"distance_cm": 5}
    assert "move_forward requested 5 cm. Action result:" in build_fallback_summary(
        "q", log
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "If I moved forward I would hit the obstacle.",
        "I have not moved the robot.",
        "I never moved because the route is blocked.",
        "Once I moved closer I could read the box again.",
    ],
)
def test_a_denied_or_hypothetical_move_is_not_an_assertion(sentence: str) -> None:
    assert undisclosed_actions(sentence, []) == []


def test_an_unqualified_claim_that_the_robot_moved_is_still_caught() -> None:
    assert undisclosed_actions("The robot moved forward 100 cm.", [])
    assert undisclosed_actions("I moved forward 100 cm.", [])


def _ultrasonic_registry(
    value: float, status: str = "clear", lidar_cm: float = 250
) -> dict:
    registry = fake_registry(lidar_envelope(lidar_cm))
    registry["read_ultrasonic"] = lambda: {
        **lidar_envelope(value, status, "ultrasonic_front"),
        "tool": "read_ultrasonic",
    }
    return registry


def test_a_clear_ultrasonic_at_its_range_cannot_vouch_for_a_longer_move() -> None:
    """It sees 200 cm and no further, so a longer move than range minus margin is not verified.

    An earlier version let a reading at the range pass; Role 4 showed that lets a move run into
    an obstacle just beyond the range that the LiDAR cannot see (glass).
    """
    check = recheck_before_action(
        "move_forward", {"distance_cm": 190}, _ultrasonic_registry(200)
    )
    assert check is not None and check.cancel is not None
    assert "ultrasonic" in check.cancel and "220" in check.cancel


def test_a_move_within_the_ultrasonic_range_still_passes_when_both_sensors_are_clear() -> (
    None
):
    check = recheck_before_action(
        "move_forward", {"distance_cm": 100}, _ultrasonic_registry(200)
    )
    assert check is not None and check.cancel is None


def test_glass_just_beyond_the_ultrasonic_range_cannot_be_driven_into() -> None:
    """Role 4's repro: glass at 215-218 cm, LiDAR sees through it (400 cm), ultrasonic reads 200."""
    import json
    from pathlib import Path

    from sensorimotor import create_sensorimotor

    path = (
        Path(__file__).parents[2]
        / "sensorimotor/scenarios/scenario_t05_sensor_disagreement.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    config["obstacles"][0].update(x_min=215, x_max=218)
    config["sensors"]["lidar"][0]["max_range_cm"] = 400
    tools = create_sensorimotor(config).tool_registry()
    check = recheck_before_action("move_forward", {"distance_cm": 230}, tools)
    assert check is not None and check.cancel is not None
    assert [r["result"]["data"]["value"] for r in check.details["reads"]] == [400, 200]
    assert (
        tools["get_position"]()["data"]["value"]["x"] == 0
    )  # the move was never dispatched
