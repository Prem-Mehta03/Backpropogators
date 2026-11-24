"""Claim check: answers may only claim writes that the tool log shows (no network)."""

from __future__ import annotations

from typing import Any

from procedural.agent import run_agent
from procedural.claims import unbacked_write_claims
from scripts.tool_wiring import build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say

REGISTRY, _ = build_tool_registry(use_real=False)


def entry(tool: str, ok: bool = True, data: Any = None) -> dict[str, Any]:
    error = None if ok else {"code": "INTERNAL", "message": "x", "retryable": False}
    return {
        "tool": tool,
        "args": {},
        "result": {"ok": ok, "data": data, "error": error},
    }


READS = [entry("query_belief", data=[{"belief_id": "b_000002"}]), entry("read_camera")]
FAKE_WRITES = (
    "The box is brown.\n- Downgraded belief b_000002 (red, user) to confidence 0.4.\n"
    "- Updated belief: box_01 color = brown, source = camera_front.\n"
    "Memory status: new belief recorded as active."
)


def test_claimed_downgrade_and_update_without_calls_are_flagged() -> None:
    problems = unbacked_write_claims(FAKE_WRITES, READS)
    assert any("downgrade" in p for p in problems)
    assert any("update" in p for p in problems)


def test_the_same_answer_is_accepted_when_the_calls_succeeded() -> None:
    log = READS + [entry("downgrade_belief"), entry("update_belief")]
    assert unbacked_write_claims(FAKE_WRITES, log) == []


def test_a_failed_write_call_does_not_back_the_claim() -> None:
    log = READS + [entry("downgrade_belief", ok=False)]
    assert any("downgrade" in p for p in unbacked_write_claims(FAKE_WRITES, log))


def test_denying_a_write_is_not_a_claim() -> None:
    answer = "The box is brown. I made no writes and left the stored beliefs unchanged."
    assert unbacked_write_claims(answer, READS) == []
    assert unbacked_write_claims("I did not downgrade anything.", READS) == []


def test_stored_evidence_wording_is_not_a_claim() -> None:
    answer = (
        "Stored evidence: the user says red (0.9). Observed: the camera says brown."
    )
    assert unbacked_write_claims(answer, READS) == []


def test_a_belief_id_no_tool_returned_is_flagged() -> None:
    problems = unbacked_write_claims("Memory holds b_000099 as blue.", READS)
    assert problems == ["you name belief ids no tool returned: b_000099"]


def test_ids_from_this_run_are_accepted() -> None:
    assert unbacked_write_claims("Memory holds b_000002 as red.", READS) == []


def test_loop_refuses_a_fabricated_write_claim_then_accepts_the_honest_answer() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "box_01"}),
            call("read_camera", {"target": "box_01"}, "call_2"),
            say(FAKE_WRITES),
            say("The box is brown. I made no memory writes in this run."),
        ]
    )
    out = run_agent("What color is box_01?", llm, REGISTRY)
    assert out.finished and out.claim_nudges == 1
    assert out.answer.startswith("The box is brown. I made no memory writes")
    assert "not accepted" in llm.seen[3][-1]["content"]


def test_a_real_write_missing_from_the_answer_is_flagged() -> None:
    log = READS + [entry("update_belief", data={"belief_id": "b_000005"})]
    answer = "The box is brown. I recorded the camera reading."
    problems = unbacked_write_claims(answer, log, require_written_ids=True)
    expected = (
        "you wrote belief(s) b_000005 but your answer does not name them; "
        "name every belief you downgraded or recorded"
    )
    assert problems == [expected]
    assert (
        unbacked_write_claims(answer, log) == []
    )  # off by default (scripted test answers)


def test_every_written_id_named_in_the_answer_is_accepted() -> None:
    log = READS + [
        entry("downgrade_belief", data={"belief_id": "b_000004"}),
        entry("update_belief", data={"belief_id": "b_000005"}),
    ]
    answer = "Downgraded b_000002 to b_000004 and recorded b_000005."
    assert unbacked_write_claims(answer, log, require_written_ids=True) == []


def test_loop_with_require_written_ids_refuses_an_answer_that_omits_a_write() -> None:
    update = {
        "subject": "box_01",
        "predicate": "color",
        "object": "brown",
        "source": "user",
        "confidence": 0.9,
        "perspective": "user",
        "reason": "person said so",
    }
    script = [
        call("query_belief", {"subject": "box_01"}),
        call("read_camera", {"target": "box_01"}, "call_2"),
        call("update_belief", update, "call_3"),
    ]
    quiet = ScriptedLLM([*script, say("The box is brown.")])
    assert run_agent(
        "What color is box_01?", quiet, REGISTRY
    ).finished  # default: accepted
    strict = ScriptedLLM(
        [*script, say("The box is brown."), say("Brown. I recorded b_000124.")]
    )
    out = run_agent("What color is box_01?", strict, REGISTRY, require_written_ids=True)
    assert out.finished and out.claim_nudges == 1
