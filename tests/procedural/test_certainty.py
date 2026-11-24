"""Certainty check (T04): no "clear" as fact on a weak or disagreeing distance reading."""

from __future__ import annotations

import pytest

from procedural.certainty import (
    already_stale,
    overclaimed_certainty,
    undisclosed_stale_belief,
    unrecorded_disagreement,
    weak_or_disputed_reason,
)
from procedural.claims import unbacked_write_claims


def reading(sensor: str, value: float, status: str, confidence: float) -> dict:
    data = {
        "schema_version": "1.1",
        "sensor": sensor,
        "value": value,
        "unit": "cm",
        "status": status,
        "timestamp": "2026-10-03T09:16:00Z",
        "confidence": confidence,
    }
    tool = "read_ultrasonic" if sensor == "ultrasonic_front" else "read_lidar"
    return {
        "tool": tool,
        "args": {},
        "result": {"ok": True, "data": data, "error": None, "tool": tool},
    }


WEAK = [reading("lidar_front", 12, "blocked", 0.4)]
STRONG = [reading("lidar_front", 12, "blocked", 0.98)]
DISAGREE = [
    reading("lidar_front", 250, "clear", 0.98),
    reading("ultrasonic_front", 15, "blocked", 0.85),
]
CAUTIOUS = (
    "I cannot confirm the route is clear. My stored map says clear, but the LiDAR read 12 cm "
    "(blocked) with confidence 0.4, which is too weak to overrule it. The evidence conflicts, "
    "so please recheck the sensor."
)


def test_a_weak_reading_and_disagreeing_sensors_are_detected() -> None:
    assert "0.4" in (weak_or_disputed_reason(WEAK) or "")
    assert "disagree" in (weak_or_disputed_reason(DISAGREE) or "")
    assert weak_or_disputed_reason(STRONG) is None
    assert weak_or_disputed_reason([]) is None


@pytest.mark.parametrize(
    "answer",
    [
        "Yes, the route is clear. The LiDAR reading is weak but the map says clear.",
        "The route is considered clear.",
        "The path is clear. My LiDAR confidence is only 0.4 and the map says clear.",
    ],
)
def test_the_live_t04_answers_are_refused(answer: str) -> None:
    problems = overclaimed_certainty(answer, WEAK)
    assert any("as fact" in p for p in problems)


def test_a_cautious_answer_is_accepted() -> None:
    assert overclaimed_certainty(CAUTIOUS, WEAK) == []
    assert overclaimed_certainty(CAUTIOUS, DISAGREE) == []


def test_a_cautious_start_without_the_required_words_is_refused() -> None:
    problems = overclaimed_certainty("I cannot say. The map says clear.", WEAK)
    assert any("'conflict'" in p for p in problems)
    assert any("weak or low confidence" in p for p in problems)
    assert any("recheck" in p for p in problems)


def test_solid_evidence_is_not_second_guessed() -> None:
    assert (
        overclaimed_certainty("No, the route is blocked: the LiDAR read 12 cm.", STRONG)
        == []
    )
    assert (
        overclaimed_certainty(
            "Yes, the route is clear.", [reading("lidar_front", 250, "clear", 0.98)]
        )
        == []
    )


def test_a_sentence_attributed_to_the_map_is_not_a_claim_by_the_agent() -> None:
    answer = (
        "My stored map says the route is clear, but the evidence conflicts: the LiDAR is weak "
        "at 0.4. Please recheck."
    )
    assert overclaimed_certainty(answer, WEAK) == []


def test_the_claim_check_reports_it_so_the_agent_refuses_the_answer() -> None:
    assert unbacked_write_claims("Yes, the route is clear.", WEAK)
    assert unbacked_write_claims(CAUTIOUS, WEAK) == []


# ---- the whole loop, with the answers Asvin saw live (T04: LiDAR 12 cm blocked, confidence 0.4)
def _belief() -> dict:
    return {
        "schema_version": "1.1",
        "belief_id": "b_000001",
        "subject": "path_A",
        "predicate": "status",
        "object": "clear",
        "source": "default_map",
        "confidence": 1.0,
        "timestamp": "2026-10-03T09:15:00Z",
        "perspective": "historical",
        "status": "active",
        "valid_from": "2026-10-03T09:15:00Z",
        "valid_to": None,
        "supersedes": None,
    }


def _envelope(tool: str, data: object) -> dict:
    return {
        "schema_version": "1.1",
        "tool": tool,
        "ok": True,
        "data": data,
        "error": None,
        "timestamp": "2026-10-03T09:16:00Z",
    }


def _t04_registry() -> dict:
    weak = reading("lidar_front", 12, "blocked", 0.4)["result"]["data"]
    return {
        "query_belief": lambda **kw: _envelope("query_belief", [_belief()]),
        "read_lidar": lambda **kw: _envelope("read_lidar", weak),
    }


def _run(answers: list[str]):
    from procedural.agent import run_agent
    from tests.procedural.scripted_llm import ScriptedLLM, call, say

    steps = [
        call("query_belief", {"subject": "path_A"}),
        call("read_lidar", {}),
        *[say(a) for a in answers],
    ]
    return run_agent("Is your route clear?", ScriptedLLM(steps), _t04_registry())


def test_a_cautious_first_answer_is_accepted_without_refusals() -> None:
    out = _run([CAUTIOUS])
    assert out.finished and out.claim_nudges == 0 and out.answer_source == "llm"


def test_the_live_t04_answer_is_refused_then_a_cautious_one_is_accepted() -> None:
    out = _run(["Yes, the route is clear. The LiDAR reading is weak.", CAUTIOUS])
    assert out.finished and out.claim_nudges == 1 and out.answer_source == "llm"
    assert "cannot confirm" in out.answer


def test_a_model_that_keeps_saying_yes_gets_the_summary_that_states_the_weakness() -> (
    None
):
    out = _run(["Yes, the route is clear."] * 4)
    assert out.finished and out.answer_source == "fallback_summary"
    assert overclaimed_certainty(out.answer, _t04_log(out)) == []
    assert "weak and conflicting" in out.answer and "recheck" in out.answer
    assert "No disagreement" not in out.answer


def _t04_log(out) -> list:
    return out.tool_calls


@pytest.mark.parametrize(
    "wording",
    [
        "A stronger observation is needed.",  # said live by the scripted S04 fixture
        "Please read the sensors again.",
        "We need more data before relying on it.",
        "I recommend re‑reading the sensors or obtaining additional evidence.",  # live T05
    ],
)
def test_wording_without_recheck_or_another_reading_is_not_enough(wording: str) -> None:
    answer = f"The map and the weak LiDAR conflict. {wording}"
    assert any("recheck" in p for p in overclaimed_certainty(answer, WEAK))


@pytest.mark.parametrize(
    "wording",
    [
        "Please recheck the sensor.",
        "Another reading would settle this.",
        "A re‑check is needed.",  # the non-breaking hyphen the model really writes
    ],
)
def test_recheck_or_another_reading_is_enough(wording: str) -> None:
    answer = f"The map and the weak LiDAR conflict. {wording}"
    assert overclaimed_certainty(answer, WEAK) == []


def test_the_live_t04_answer_that_lacked_the_word_conflict_is_refused() -> None:
    live = (
        "I cannot confirm whether the route is clear. My stored belief says clear, but the lidar "
        "reads blocked with confidence 0.4. The lidar confidence is below 0.6, so it is too weak "
        "to override the stored belief. Please re‑read the sensors to obtain stronger evidence."
    )
    problems = overclaimed_certainty(live, WEAK)
    assert any("'conflict'" in p for p in problems) and any(
        "recheck" in p for p in problems
    )


# ---- T05: disagreeing sensors must be recorded so memory can mark the state disputed
def _update(source: str, ok: bool = True) -> dict:
    return {
        "tool": "update_belief",
        "args": {"source": source},
        "result": {"ok": ok, "data": None, "error": None if ok else {"code": "X"}},
    }


def test_disagreeing_sensors_must_both_be_recorded_before_the_answer() -> None:
    assert unrecorded_disagreement(DISAGREE)
    only_one = [*DISAGREE, _update("lidar_front")]
    problem = unrecorded_disagreement(only_one)[0]
    assert "ultrasonic_front" in problem and "lidar_front, " not in problem
    both = [*DISAGREE, _update("lidar_front"), _update("ultrasonic_front")]
    assert unrecorded_disagreement(both) == []
    failed = [*DISAGREE, _update("lidar_front"), _update("ultrasonic_front", ok=False)]
    assert unrecorded_disagreement(failed)


def test_no_recording_is_demanded_for_a_weak_reading_or_solid_evidence() -> None:
    assert unrecorded_disagreement(WEAK) == []
    assert unrecorded_disagreement(STRONG) == []


# ---- T06: an entry that was already superseded must be called stale
def _history(*beliefs: dict) -> dict:
    return {
        "tool": "get_belief_history",
        "args": {"subject": "path_A"},
        "result": {"ok": True, "data": list(beliefs), "error": None},
    }


OLD = {
    "belief_id": "b_000001",
    "subject": "path_A",
    "status": "superseded",
    "source": "default_map",
    "timestamp": "2026-09-01T09:00:00Z",
    "valid_to": "2026-10-02T09:16:00Z",
}
NEW = {
    **OLD,
    "belief_id": "b_000002",
    "status": "active",
    "source": "floor_plan_rev2",
    "valid_to": None,
}
STALE_LOG = [_history(OLD, NEW), reading("lidar_front", 250, "clear", 0.98)]


def test_the_live_t06_answer_without_the_word_stale_is_refused() -> None:
    live = (
        "Yes, the route is clear. b_000001 - status blocked (default_map, 2026-09-01, status "
        "superseded); b_000002 - clear (floor_plan_rev2). The LiDAR agrees."
    )
    problems = undisclosed_stale_belief(live, STALE_LOG)
    assert problems and "b_000001" in problems[0] and "stale or outdated" in problems[0]


def test_an_answer_that_calls_the_old_entry_stale_with_its_date_is_accepted() -> None:
    good = "Yes, the route is clear. The 2026-09-01 default_map entry is stale; floor_plan_rev2 is newer."
    assert undisclosed_stale_belief(good, STALE_LOG) == []
    no_date_or_source = "Yes, the route is clear. The old entry is stale."
    assert undisclosed_stale_belief(no_date_or_source, STALE_LOG)


def test_the_runs_own_supersession_is_not_stale() -> None:
    log = [
        _history(NEW),
        {
            "tool": "downgrade_belief",
            "args": {},
            "result": {"ok": True, "data": {}, "error": None},
        },
        _history(OLD, NEW),  # looked up after this run's own write
    ]
    assert already_stale(log) == []
    assert undisclosed_stale_belief("No, the route is blocked.", log) == []


def test_a_disagreement_found_only_by_the_recheck_before_a_move_needs_no_memory_write() -> (
    None
):
    lidar = reading("lidar_front", 250, "clear", 0.98)
    move = {
        "tool": "move_forward",
        "args": {"distance_cm": 20},
        "result": {
            "ok": False,
            "data": None,
            "error": {"code": "CONFLICT", "message": "x"},
        },
        "guard": {
            "recheck": {"reads": [reading("ultrasonic_front", 15, "blocked", 0.85)]},
        },
    }
    log = [lidar, move]
    assert weak_or_disputed_reason(log) is not None  # still needs the conflict wording
    assert unrecorded_disagreement(log) == []


def test_for_disagreeing_sensors_asking_for_more_evidence_is_enough() -> None:
    answer = "The LiDAR and the ultrasonic sensor disagree. I need more evidence."
    assert overclaimed_certainty(answer, DISAGREE) == []
    assert any(
        "recheck" in p for p in overclaimed_certainty(answer, WEAK)
    )  # not for a weak reading
