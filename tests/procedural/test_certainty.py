"""Certainty check (T04): no "clear" as fact on a weak or disagreeing distance reading."""

from __future__ import annotations

import pytest

from procedural.certainty import overclaimed_certainty, weak_or_disputed_reason
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


def test_a_cautious_start_without_conflict_or_recheck_wording_is_refused() -> None:
    problems = overclaimed_certainty("I cannot say. The map says clear.", WEAK)
    assert any("conflicts or is weak" in p for p in problems) is True
    assert any("again or getting more evidence" in p for p in problems)


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
    assert (
        "weak or conflicting" in out.answer and "read the sensors again" in out.answer
    )
    assert "No disagreement" not in out.answer


def _t04_log(out) -> list:
    return out.tool_calls


@pytest.mark.parametrize(
    "wording",
    [
        "A stronger observation is needed.",
        "Please read the sensors again.",
        "We need more data before relying on it.",
        "Another reading would settle this.",
    ],
)
def test_the_usual_ways_to_ask_for_more_evidence_are_accepted(wording: str) -> None:
    answer = f"The map and the weak LiDAR disagree. {wording}"
    assert overclaimed_certainty(answer, WEAK) == []
