"""ReAct loop on the scripted fake LLM: call order, step limit, bad model output."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from procedural.agent import AgentResult
from procedural.agent import run_agent as _run_agent
from procedural.llm_client import LLMClientError, LLMResponse, ToolCall
from procedural.prompts import MISSING_REPLY_NOTE, SYSTEM_PROMPT
from procedural.state import subjects_outside
from scripts.tool_wiring import build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say


def run_agent(*args: Any, **kwargs: Any) -> AgentResult:
    """These tests exercise the loop itself, so the evidence checklist is switched off here.

    The checklist has its own tests in test_checklist_enforcement.py.
    """
    kwargs.setdefault("required_evidence", ())
    return _run_agent(*args, **kwargs)


REGISTRY, _ = build_tool_registry(use_real=False)
QUESTION = "Is your route clear? Justify your response by inspecting your internal system layers."


def _tool_messages(llm: ScriptedLLM, call_index: int) -> list[dict]:
    return [m for m in llm.seen[call_index] if m["role"] == "tool"]


def test_route_question_uses_memory_then_sensor_then_answers() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A", "predicate": "status"}),
            call("read_lidar", {}, "call_2"),
            say(
                "No. Memory says clear (default_map, 1.0) but LiDAR reads 12 cm, blocked."
            ),
        ]
    )
    out = run_agent(QUESTION, llm, REGISTRY)

    assert out.finished and out.error is None
    assert [c["tool"] for c in out.tool_calls] == ["query_belief", "read_lidar"]
    assert [c["step"] for c in out.tool_calls] == [1, 2]
    assert out.tool_calls[1]["result"]["data"]["value"] == 12
    assert out.model_calls == 3 and "12 cm" in out.answer
    assert [m["role"] for m in out.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]


def test_model_sees_each_tool_result_with_the_matching_call_id() -> None:
    llm = ScriptedLLM([call("read_lidar", {}, "abc"), say("12 cm")])
    run_agent("lidar?", llm, REGISTRY)
    (msg,) = _tool_messages(llm, 1)
    assert msg["tool_call_id"] == "abc" and json.loads(msg["content"])["ok"] is True


def test_several_tool_calls_in_one_reply_are_all_run_in_order() -> None:
    both = LLMResponse(
        None,
        [
            ToolCall("a", "query_belief", {"subject": "path_A"}),
            ToolCall("b", "read_lidar", {}),
        ],
    )
    llm = ScriptedLLM([both, say("done")])
    out = run_agent(QUESTION, llm, REGISTRY)
    assert [c["tool"] for c in out.tool_calls] == ["query_belief", "read_lidar"]
    assert [m["tool_call_id"] for m in _tool_messages(llm, 1)] == ["a", "b"]
    assert out.model_calls == 2


def test_answering_without_tools_is_allowed_when_the_checklist_is_off() -> None:
    out = run_agent(QUESTION, ScriptedLLM([say("Probably clear.")]), REGISTRY)
    assert out.finished and out.tool_calls == [] and out.answer == "Probably clear."


def test_step_limit_stops_a_model_that_never_answers() -> None:
    llm = ScriptedLLM([call("read_lidar", {}, f"c{i}") for i in range(20)])
    out = run_agent(QUESTION, llm, REGISTRY, max_steps=4)
    assert out.error is not None
    assert not out.finished and out.error["code"] == "STEP_LIMIT"
    assert out.model_calls == 4 and len(out.tool_calls) == 4 and out.answer == ""


def test_empty_reply_gets_a_nudge_and_counts_as_a_step() -> None:
    llm = ScriptedLLM([LLMResponse(None), LLMResponse("   "), say("ok")])
    out = run_agent(QUESTION, llm, REGISTRY)
    assert out.finished and out.answer == "ok" and out.model_calls == 3
    notes = [
        m
        for m in llm.seen[1]
        if m["role"] == "user" and m["content"] == MISSING_REPLY_NOTE
    ]
    assert len(notes) == 1


def test_endless_empty_replies_end_in_step_limit() -> None:
    out = run_agent(
        QUESTION, ScriptedLLM([LLMResponse(None)] * 10), REGISTRY, max_steps=3
    )
    assert out.error is not None
    assert out.error["code"] == "STEP_LIMIT" and out.model_calls == 3


def test_malformed_arguments_are_reported_to_the_model_which_can_retry() -> None:
    bad = LLMResponse(
        None, [ToolCall("c1", "read_lidar", {}, "Expecting property name")]
    )
    llm = ScriptedLLM([bad, call("read_lidar", {}, "c2"), say("12 cm")])
    out = run_agent(QUESTION, llm, REGISTRY)
    first = json.loads(_tool_messages(llm, 1)[0]["content"])
    assert first["ok"] is False and "Malformed" in first["error"]["message"]
    assert [c["result"]["ok"] for c in out.tool_calls] == [False, True] and out.finished


def test_unknown_tool_and_bad_arguments_come_back_as_invalid_argument() -> None:
    llm = ScriptedLLM(
        [
            call("fly", {}),
            call("move_forward", {"distance_cm": "far"}, "c2"),
            say("cannot"),
        ]
    )
    out = run_agent("move", llm, REGISTRY)
    codes = [c["result"]["error"]["code"] for c in out.tool_calls]
    assert codes == ["INVALID_ARGUMENT", "INVALID_ARGUMENT"] and out.finished


def test_a_tool_error_is_not_a_run_error() -> None:
    llm = ScriptedLLM(
        [call("query_belief", {"subject": "ghost"}), say("Evidence is missing.")]
    )
    out = run_agent("What is ghost?", llm, REGISTRY)
    assert out.tool_calls[0]["result"]["error"]["code"] == "NOT_FOUND"
    assert out.finished and "missing" in out.answer


def test_llm_failure_becomes_internal_error_not_an_exception() -> None:
    llm = ScriptedLLM([call("read_lidar", {}), LLMClientError("rate limited")])
    out = run_agent(QUESTION, llm, REGISTRY)
    assert out.error is not None
    assert not out.finished and out.error["code"] == "INTERNAL"
    assert "rate limited" in out.error["message"] and len(out.tool_calls) == 1


def test_runs_are_independent() -> None:
    first = run_agent("a", ScriptedLLM([call("read_lidar", {}), say("x")]), REGISTRY)
    second = run_agent("b", ScriptedLLM([say("y")]), REGISTRY)
    assert (
        len(first.tool_calls) == 1
        and second.tool_calls == []
        and second.question == "b"
    )


SUBJECTS = {"path_A": "the path ahead", "robot": "this robot"}


def test_known_subjects_are_listed_in_the_system_message() -> None:
    llm = ScriptedLLM([say("ok")])
    run_agent(QUESTION, llm, REGISTRY, known_subjects=SUBJECTS)
    system = llm.seen[0][0]
    assert (
        system["role"] == "system" and "- path_A: the path ahead" in system["content"]
    )


def test_default_system_message_is_the_standard_prompt() -> None:
    llm = ScriptedLLM([say("ok")])
    run_agent(QUESTION, llm, REGISTRY)
    assert llm.seen[0][0]["content"] == SYSTEM_PROMPT


def test_explicit_system_prompt_overrides_the_glossary() -> None:
    llm = ScriptedLLM([say("ok")])
    run_agent(QUESTION, llm, REGISTRY, system_prompt="CUSTOM", known_subjects=SUBJECTS)
    assert llm.seen[0][0]["content"] == "CUSTOM"


def test_unknown_subject_is_warned_about_but_not_blocked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "route"}),
            call("query_belief", {"subject": "path_A"}, "call_2"),
            say("done"),
        ]
    )
    with caplog.at_level(logging.WARNING, logger="procedural.agent"):
        out = run_agent(QUESTION, llm, REGISTRY, known_subjects=SUBJECTS)
    assert (
        len([r for r in caplog.records if "unknown subject 'route'" in r.getMessage()])
        == 1
    )
    assert [c["result"]["ok"] for c in out.tool_calls] == [
        False,
        True,
    ]  # both really ran
    assert subjects_outside(out.tool_calls, SUBJECTS) == ["route"]


def test_no_warning_for_known_subjects_or_when_no_list_is_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="procedural.agent"):
        run_agent(
            QUESTION,
            ScriptedLLM([call("query_belief", {"subject": "path_A"}), say("x")]),
            REGISTRY,
            known_subjects=SUBJECTS,
        )
        run_agent(
            QUESTION,
            ScriptedLLM([call("query_belief", {"subject": "route"}), say("x")]),
            REGISTRY,
        )
    assert not [r for r in caplog.records if "unknown subject" in r.getMessage()]
