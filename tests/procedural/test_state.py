"""Agent state: messages, tool log in test-log format, evidence bookkeeping."""

from __future__ import annotations

import json

from procedural.llm_client import ToolCall
from procedural.state import new_agent_state, subjects_outside
from procedural.tools import error_result
from scripts.tool_wiring import build_tool_registry

REGISTRY, _ = build_tool_registry(use_real=False)


def test_new_state_starts_with_system_and_user_messages() -> None:
    state = new_agent_state("Q?", "SYS")
    assert [m["role"] for m in state.messages] == ["system", "user"]
    assert state.messages[1]["content"] == "Q?" and state.model_calls == 0


def test_two_states_do_not_share_anything() -> None:
    a, b = new_agent_state("a", "s"), new_agent_state("b", "s")
    a.add_user_note("note")
    assert len(b.messages) == 2 and a.tool_log is not b.tool_log


def test_assistant_turn_with_and_without_tool_calls() -> None:
    state = new_agent_state("Q", "S")
    state.add_assistant_turn(
        None, [ToolCall("c1", "read_lidar", {"direction": "front"})]
    )
    state.add_assistant_turn("done", [])
    first, second = state.messages[-2:]
    assert first["content"] == "" and first["tool_calls"][0]["id"] == "c1"
    assert json.loads(first["tool_calls"][0]["function"]["arguments"]) == {
        "direction": "front"
    }
    assert "tool_calls" not in second and second["content"] == "done"


def test_tool_results_are_logged_in_test_log_format_and_added_to_messages() -> None:
    state = new_agent_state("Q", "S")
    call = ToolCall("c1", "read_lidar", {})
    envelope = REGISTRY["read_lidar"]()
    state.add_tool_result(call, envelope)
    state.add_tool_result(
        ToolCall("c2", "get_position", {}), REGISTRY["get_position"]()
    )
    assert [e["step"] for e in state.tool_log] == [1, 2]
    assert set(state.tool_log[0]) == {"step", "tool", "args", "result"}
    assert state.messages[-2]["tool_call_id"] == "c1"
    assert state.tools_called() == ["read_lidar", "get_position"]


def test_has_evidence_from_needs_ok_and_non_empty_data() -> None:
    state = new_agent_state("Q", "S")
    state.add_tool_result(
        ToolCall("c1", "query_belief", {}),
        error_result("query_belief", "NOT_FOUND", "x"),
    )
    assert not state.has_evidence_from("query_belief")
    state.add_tool_result(
        ToolCall("c2", "detect_conflict", {}), REGISTRY["detect_conflict"]("a", "b")
    )
    assert not state.has_evidence_from("detect_conflict")  # ok, but an empty list
    state.add_tool_result(ToolCall("c3", "read_lidar", {}), REGISTRY["read_lidar"]())
    assert state.has_evidence_from("read_lidar") and not state.has_evidence_from(
        "read_camera"
    )


def _entry(tool: str, args: dict) -> dict:
    return {"step": 1, "tool": tool, "args": args, "result": {}}


def test_subjects_outside_lists_unknown_memory_subjects_in_order() -> None:
    log = [
        _entry("query_belief", {"subject": "route"}),
        _entry("read_lidar", {"direction": "front"}),
        _entry("query_belief", {"subject": "path_A"}),
        _entry("detect_conflict", {"subject": "route", "predicate": "status"}),
    ]
    assert subjects_outside(log, {"path_A", "robot"}) == ["route", "route"]


def test_subjects_outside_is_empty_when_all_known_or_no_memory_calls() -> None:
    assert (
        subjects_outside([_entry("query_belief", {"subject": "path_A"})], {"path_A"})
        == []
    )
    assert subjects_outside([_entry("read_lidar", {})], {"path_A"}) == []
    assert subjects_outside([], {"path_A"}) == []
