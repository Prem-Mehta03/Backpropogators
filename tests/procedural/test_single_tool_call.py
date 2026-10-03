"""One tool round end to end, using the scripted fake LLM (no API key needed)."""

from __future__ import annotations

import json
import os

import pytest

from procedural.llm_client import LLMClient, LLMResponse, ToolCall
from procedural.single_tool_call import run_single_tool_call
from sensorimotor import stub
from tests.procedural.scripted_llm import ScriptedLLM

QUESTION = "What does your front LiDAR currently read?"
REGISTRY = {"read_lidar": stub.read_lidar}


def _lidar_call(args: dict | None = None, error: str | None = None) -> LLMResponse:
    return LLMResponse(None, [ToolCall("call_1", "read_lidar", args or {}, error)])


def test_happy_path_message_sequence_and_result() -> None:
    llm = ScriptedLLM(
        [_lidar_call({"direction": "front"}), LLMResponse("Front LiDAR: 12 cm, blocked, 0.98.")]
    )
    out = run_single_tool_call(llm, QUESTION, REGISTRY)

    assert out.tool_was_called
    assert [c["tool"] for c in out.tool_calls] == ["read_lidar"]
    assert out.tool_calls[0]["result"]["data"]["value"] == 12
    roles = [m["role"] for m in out.messages]
    assert roles == ["system", "user", "assistant", "tool"]
    tool_msg = out.messages[-1]
    assert tool_msg["tool_call_id"] == out.messages[2]["tool_calls"][0]["id"]
    assert json.loads(tool_msg["content"])["ok"] is True
    assert "12" in out.answer


def test_second_model_call_cannot_start_another_tool_call() -> None:
    llm = ScriptedLLM([_lidar_call(), LLMResponse("ok")])
    run_single_tool_call(llm, QUESTION, REGISTRY)
    assert llm.tool_choices == [None, "none"]


def test_model_that_skips_the_tool_is_visible_to_the_caller() -> None:
    llm = ScriptedLLM([LLMResponse("It is probably clear.")])
    out = run_single_tool_call(llm, QUESTION, REGISTRY)
    assert out.tool_was_called is False and len(llm.seen) == 1


def test_malformed_arguments_reach_the_model_as_an_error_envelope() -> None:
    llm = ScriptedLLM(
        [_lidar_call(error="Expecting property name"), LLMResponse("Could not read.")]
    )
    out = run_single_tool_call(llm, QUESTION, REGISTRY)
    envelope = json.loads(llm.seen[1][-1]["content"])
    assert envelope["ok"] is False and envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert "Malformed" in envelope["error"]["message"] and out.answer == "Could not read."


def test_error_envelope_from_the_sensor_is_given_to_the_model_unchanged() -> None:
    llm = ScriptedLLM([_lidar_call({"direction": "left"}), LLMResponse("No data.")])
    run_single_tool_call(llm, QUESTION, REGISTRY)
    envelope = json.loads(llm.seen[1][-1]["content"])
    assert envelope["ok"] is False and envelope["data"] is None


@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="needs GROQ_API_KEY (live test)")
def test_live_model_calls_read_lidar() -> None:
    out = run_single_tool_call(LLMClient(), QUESTION, REGISTRY)
    assert out.tool_was_called
    assert out.tool_calls[0]["tool"] == "read_lidar"
