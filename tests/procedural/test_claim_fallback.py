"""P2: the Scenario B step-limit fix (claim-check false positives and the fallback summary).

What failed on 13 Oct: a read-only Scenario B run (query_belief + read_camera, no writes) was
refused 8 times and hit STEP_LIMIT. The prompt told the model to "always finish with a Memory
status line" and gave b_000006 as the example, so a model with no write to report copied the
invented id, and the claim check refused it every time. These tests replay that situation on the
real declarative and sensorimotor layers with a scripted model (no network, no API key).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from procedural.agent import MAX_CLAIM_REFUSALS, run_agent
from procedural.claims import (
    effective_statuses,
    returned_belief_ids,
    unbacked_write_claims,
    wrong_active_claims,
)
from procedural.fallback_summary import build_fallback_summary
from procedural.prompts import SYSTEM_PROMPT, build_claim_note
from scripts.tool_wiring import build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say

QUESTION_B = (
    "What color does the user think the object is, what color do you register it as, and "
    "what does your data history say its true state is?"
)
ROUTE = "Is your route clear? Justify your response by inspecting your internal system layers."
# The line prompt v5 told the model to write, with its made-up id: what the model copied.
PROMPT_COPY = (
    "The user thinks red, the camera sees brown and the history says blue.\n"
    "Memory status: b_000006 (brown, camera_front) is recorded as disputed, not settled."
)
GOOD_READ_ONLY = (
    "The user thinks red (b_000002), the camera registers brown and the history says blue "
    "(b_000003). I made no memory writes."
)


def entry(tool: str, ok: bool = True, data: Any = None, message: str = "x") -> dict:
    error = (
        None
        if ok
        else {"code": "INVALID_ARGUMENT", "message": message, "retryable": False}
    )
    return {
        "tool": tool,
        "args": {},
        "result": {"ok": ok, "data": data, "error": error},
    }


def scenario_b_reads() -> list:
    return [
        call("query_belief", {"subject": "box_01"}),
        call("read_camera", {"target": "box_01"}, "c2"),
    ]


# ---------------------------------------------------------------- the prompt
def test_prompt_contains_no_example_belief_id() -> None:
    assert re.search(r"\bb_\d{3,}\b", SYSTEM_PROMPT) is None


def test_prompt_tells_the_model_to_skip_the_status_line_when_nothing_was_written() -> (
    None
):
    assert "If you made no writes, do not write a Memory status line" in SYSTEM_PROMPT


def test_claim_note_tells_the_model_how_to_fix_an_invented_id() -> None:
    note = build_claim_note(["you name belief ids no tool returned: b_000006"])
    assert "Name only belief ids that appear in tool results" in note


# ------------------------------------------------------ the claim check itself
READS = [entry("query_belief", data=[{"belief_id": "b_000002"}]), entry("read_camera")]


def test_the_prompt_copy_line_is_still_refused() -> None:
    problems = unbacked_write_claims(PROMPT_COPY, READS)
    assert problems == ["you name belief ids no tool returned: b_000006"]


def test_describing_what_memory_holds_is_not_a_write_claim() -> None:
    for sentence in (
        "The camera reading is recorded in memory as brown.",
        "The user's belief is recorded in memory as red (b_000002).",
        "Memory status: b_000002 (red, user) is recorded as active.",
        "Tell me which view is correct and I will record your answer as a belief.",
    ):
        assert unbacked_write_claims(sentence, READS) == [], sentence


def test_real_update_claims_are_still_caught() -> None:
    for sentence in (
        "I recorded the reading in memory.",
        "I have updated my belief graph.",
        "Updated belief: box_01 color = brown.",
        "Memory has been updated with the new reading.",
        "I have downgraded the stored belief and recorded a new belief.",
    ):
        problems = unbacked_write_claims(sentence, READS)
        assert any("update" in p or "downgrade" in p for p in problems), sentence


def test_an_id_only_in_an_error_message_or_in_arguments_does_not_count() -> None:
    refused = entry(
        "downgrade_belief", ok=False, message="belief_id b_000099 was not returned"
    )
    refused["args"] = {"belief_id": "b_000099"}
    log = READS + [refused]
    assert returned_belief_ids(log) == {"b_000002"}
    assert unbacked_write_claims("Memory holds b_000099.", log) == [
        "you name belief ids no tool returned: b_000099"
    ]


# -------------------------------------------- the loop, on the real layers (Scenario B)
def test_scenario_b_copying_the_prompt_line_ends_in_the_fallback_not_step_limit() -> (
    None
):
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM(
        [*scenario_b_reads(), *[say(PROMPT_COPY)] * (MAX_CLAIM_REFUSALS + 1)]
    )
    out = run_agent(QUESTION_B, llm, registry, require_written_ids=True)
    assert out.finished and out.error is None
    assert out.answer_source == "fallback_summary"
    assert out.claim_nudges == MAX_CLAIM_REFUSALS
    assert len(out.claim_refusals) == MAX_CLAIM_REFUSALS + 1
    assert out.claim_refusals[0]["text"] == PROMPT_COPY
    assert out.claim_refusals[0]["attempt"] == 1
    assert out.model_calls == 2 + MAX_CLAIM_REFUSALS + 1


def test_the_fallback_summary_reports_all_three_views_and_passes_the_claim_check() -> (
    None
):
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM(
        [*scenario_b_reads(), *[say(PROMPT_COPY)] * (MAX_CLAIM_REFUSALS + 1)]
    )
    out = run_agent(QUESTION_B, llm, registry, require_written_ids=True)
    for needed in (
        "red",
        "blue",
        "brown",
        "bot_02",
        "camera_front",
        "I made no memory writes",
    ):
        assert needed in out.answer
    assert "Sources that disagree:" in out.answer
    assert (
        unbacked_write_claims(out.answer, out.tool_calls, require_written_ids=True)
        == []
    )
    assert "b_000006" not in out.answer


def test_a_model_that_recovers_on_a_retry_is_not_replaced() -> None:
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM([*scenario_b_reads(), say(PROMPT_COPY), say(GOOD_READ_ONLY)])
    out = run_agent(QUESTION_B, llm, registry, require_written_ids=True)
    assert out.finished and out.answer_source == "llm"
    assert out.claim_nudges == 1 and len(out.claim_refusals) == 1
    assert out.answer == GOOD_READ_ONLY


def test_running_out_of_model_calls_after_refusals_also_uses_the_fallback() -> None:
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM([*scenario_b_reads(), *[say(PROMPT_COPY)] * 3])
    out = run_agent(QUESTION_B, llm, registry, max_steps=5, require_written_ids=True)
    assert out.finished and out.answer_source == "fallback_summary"


def test_missing_evidence_still_ends_in_step_limit_not_the_fallback() -> None:
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM([say("I think the box is red.")] * 3)
    out = run_agent(QUESTION_B, llm, registry, max_steps=3)
    assert out.error is not None and out.error["code"] == "STEP_LIMIT"
    assert out.answer_source == "llm" and out.claim_refusals == []


# --------------------------------------------- the loop, on the real layers (Scenario A)
def scenario_a_with_writes() -> list:
    return [
        call("query_belief", {"subject": "path_A"}),
        call("get_belief_history", {"subject": "path_A"}),
        call("read_lidar", {"direction": "front"}, "c2"),
        call(
            "downgrade_belief",
            {
                "belief_id": "b_000001",
                "new_confidence": 0.3,
                "reason": "live lidar disagrees",
            },
            "c3",
        ),
        call(
            "update_belief",
            {
                "subject": "path_A",
                "predicate": "status",
                "object": "blocked",
                "source": "lidar_front",
                "confidence": 0.98,
                "perspective": "agent_sensor",
                "reason": "live lidar reading",
            },
            "c4",
        ),
    ]


def test_fallback_after_real_writes_names_every_written_belief() -> None:
    registry, _ = build_tool_registry(scenario="scenario_a")
    bad = "No. I downgraded b_000001 and recorded b_000009."
    llm = ScriptedLLM(
        [*scenario_a_with_writes(), *[say(bad)] * (MAX_CLAIM_REFUSALS + 1)]
    )
    out = run_agent(ROUTE, llm, registry, require_written_ids=True)
    assert out.answer_source == "fallback_summary"
    assert "downgrade_belief wrote b_000004" in out.answer
    assert "update_belief wrote b_000005" in out.answer
    assert "lidar_front" in out.answer and "default_map" in out.answer
    assert (
        unbacked_write_claims(out.answer, out.tool_calls, require_written_ids=True)
        == []
    )


# --------------------------------------------------------- the summary on its own
def test_summary_with_no_evidence_says_so() -> None:
    text = build_fallback_summary(
        "What color is box_99?", [entry("query_belief", data=[])]
    )
    assert "Stored evidence:\n- none" in text
    assert "Observed evidence:\n- none" in text
    assert "Evidence is missing" in text


def test_summary_is_deterministic() -> None:
    log = READS
    assert build_fallback_summary("q", log) == build_fallback_summary("other q", log)


# ------------------------------- cause 2, found in a real run (2026-11-23, Scenario B)
# The model wrote "No stored belief was downgraded." and the check counted that as a claim,
# because the leading-"No" rule removed the word that made the sentence a denial. The fixture
# holds that run's real tool log and the four answers the check refused.
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "scenario_b_refused_answers.json").read_text(
        encoding="utf-8"
    )
)


def test_denials_that_start_with_no_are_not_write_claims() -> None:
    for sentence in (
        "No stored belief was downgraded.",
        "No belief was downgraded.",
        "No new belief was recorded.",
        "No downgrade was needed.",
    ):
        assert unbacked_write_claims(sentence, READS) == [], sentence


def test_an_answer_that_opens_with_no_and_then_claims_a_downgrade_is_still_caught() -> (
    None
):
    problems = unbacked_write_claims(
        "No, my route is blocked. I downgraded b_000002.", READS
    )
    assert any("downgrade" in p for p in problems)


def test_the_real_refused_answers_that_only_denied_a_downgrade_now_pass() -> None:
    log = FIXTURE["tool_calls"]
    first, _second, third, fourth = (r["text"] for r in FIXTURE["claim_refusals"])
    for text in (first, third, fourth):
        assert unbacked_write_claims(text, log, require_written_ids=True) == []


def test_the_real_answer_that_left_out_the_written_belief_is_still_refused() -> None:
    log = FIXTURE["tool_calls"]
    second = FIXTURE["claim_refusals"][1]["text"]
    problems = unbacked_write_claims(second, log, require_written_ids=True)
    assert problems and "b_000004" in problems[0] and "does not name" in problems[0]


def test_the_real_run_is_accepted_at_the_first_answer_by_the_loop() -> None:
    """Replay the run's tool calls and its first answer on the real layers: no refusal."""
    registry, _ = build_tool_registry(scenario="scenario_b")
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "box_01"}),
            call("read_camera", {"target": "box_01"}, "c2"),
            call(
                "update_belief",
                {
                    "subject": "box_01",
                    "predicate": "color",
                    "object": "brown",
                    "source": "camera_front",
                    "confidence": 0.9,
                    "perspective": "agent_sensor",
                    "reason": "Live camera reading",
                },
                "c3",
            ),
            say(FIXTURE["claim_refusals"][0]["text"]),
        ]
    )
    out = run_agent(FIXTURE["question"], llm, registry, require_written_ids=True)
    assert (
        out.answer_source == "llm"
        and out.claim_nudges == 0
        and out.claim_refusals == []
    )


def test_summary_lists_a_reading_once_when_memory_holds_it_as_a_belief() -> None:
    text = build_fallback_summary("q", FIXTURE["tool_calls"])
    line = next(x for x in text.splitlines() if x.startswith("- box_01 color:"))
    assert "camera_front (live reading)" not in line
    assert "b_000004 (agent_sensor) says brown" in line


# ------------- cause 3, found in real Scenario A runs (2026-11-23): stale "active" status
# After the downgrade the lowered copy b_000004 reads "active" in its own result; the update then
# returns b_000005 with `supersedes: b_000004`. One of three real answers still wrote
# "b_000004 (historical) is recorded as active". Three real runs are the fixture.
RUNS_A = json.loads(
    (Path(__file__).parent / "fixtures" / "scenario_a_runs.json").read_text(
        encoding="utf-8"
    )
)


def test_the_lowered_copy_counts_as_superseded_once_the_sensor_belief_is_written() -> (
    None
):
    assert effective_statuses(RUNS_A["tool_calls"]) == {
        "b_000001": "superseded",
        "b_000004": "superseded",
        "b_000005": "active",
    }


def test_the_two_correct_real_answers_pass() -> None:
    first, second, _third = RUNS_A["final_answers"]
    for text in (first, second):
        assert unbacked_write_claims(text, RUNS_A["tool_calls"], True) == []


def test_the_real_answer_that_calls_the_superseded_belief_active_is_refused() -> None:
    third = RUNS_A["final_answers"][2]
    problems = unbacked_write_claims(third, RUNS_A["tool_calls"], True)
    expected = (
        "you call b_000004 active, but this run's results show it is superseded: "
        "report its status as superseded"
    )
    assert problems == [expected]


def test_the_same_answer_with_the_status_corrected_passes() -> None:
    fixed = RUNS_A["final_answers"][2].replace(
        "Memory status: b_000004 (historical) is recorded as active.",
        "Memory status: b_000004 (historical) is recorded as superseded.",
    )
    assert fixed != RUNS_A["final_answers"][2]
    assert unbacked_write_claims(fixed, RUNS_A["tool_calls"], True) == []


def test_the_real_refusal_for_leaving_out_the_lowered_copy_is_still_raised() -> None:
    problems = unbacked_write_claims(
        RUNS_A["first_refusal"], RUNS_A["tool_calls"], True
    )
    assert (
        len(problems) == 1
        and "b_000004" in problems[0]
        and "does not name" in problems[0]
    )


def test_an_active_word_belongs_to_the_id_it_follows() -> None:
    log = RUNS_A["tool_calls"]
    for ok in (
        "I downgraded b_000001 to b_000004 and recorded b_000005 as active.",
        "b_000005 replaced b_000004 and is now active.",
        "b_000004 is no longer active.",
        "b_000004 is superseded, not active.",
    ):
        assert wrong_active_claims(ok, effective_statuses(log)) == [], ok
    assert wrong_active_claims("b_000001 is active.", effective_statuses(log)) == [
        "b_000001"
    ]


def test_a_disputed_belief_called_active_is_refused() -> None:
    disputed = {
        "belief_id": "b_000009",
        "subject": "path_A",
        "predicate": "status",
        "object": "blocked",
        "status": "disputed",
        "supersedes": None,
    }
    log = [entry("update_belief", data=disputed)]
    problems = unbacked_write_claims("I recorded b_000009; it is active.", log, True)
    assert any("b_000009 active" in p and "disputed" in p for p in problems)


def test_summary_shows_the_lowered_copy_as_superseded() -> None:
    text = build_fallback_summary("q", RUNS_A["tool_calls"])
    line = next(x for x in text.splitlines() if x.startswith("- b_000004:"))
    assert "status superseded" in line
    # both map beliefs are superseded, so nothing live still disagrees with the LiDAR
    assert "No disagreement between the sources above." in text
    # the write lines must not repeat the stale "active" of the lowered copy either
    assert (
        "downgrade_belief wrote b_000004" in text
        and "status active"
        not in text.split("Memory writes in this run:")[1]
        .split("Sources")[0]
        .split("update_belief")[0]
    )
    assert unbacked_write_claims(text, RUNS_A["tool_calls"], True) == []
