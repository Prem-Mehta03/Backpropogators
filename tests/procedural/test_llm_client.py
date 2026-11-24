"""LLM client: request settings, reply parsing, malformed arguments, failures."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from procedural.llm_client import LLMClient, LLMClientError


def _raw(content: str | None, tool_calls: list | None = None) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def _fake_api(raw: Any = None, error: Exception | None = None) -> SimpleNamespace:
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if error:
            raise error
        return raw

    api = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    api.calls = calls  # type: ignore[attr-defined]
    return api


def _tool_call(name: str, args: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="call_1", function=SimpleNamespace(name=name, arguments=args)
    )


def test_plain_reply_is_returned_without_tools_in_request() -> None:
    api = _fake_api(_raw("pong"))
    resp = LLMClient(client=api).chat([{"role": "user", "content": "ping"}])
    assert resp.content == "pong" and resp.tool_calls == []
    assert "tools" not in api.calls[0] and "tool_choice" not in api.calls[0]


def test_temperature_zero_and_tool_call_parsed() -> None:
    api = _fake_api(_raw(None, [_tool_call("read_lidar", '{"direction": "front"}')]))
    resp = LLMClient(client=api).chat(
        [{"role": "user", "content": "x"}], tools=[{"t": 1}]
    )
    assert api.calls[0]["temperature"] == 0.0
    assert api.calls[0]["tool_choice"] == "auto"
    call = resp.tool_calls[0]
    assert (call.id, call.name, call.arguments) == (
        "call_1",
        "read_lidar",
        {"direction": "front"},
    )
    assert call.arguments_error is None


def test_tool_choice_none_is_passed_through() -> None:
    api = _fake_api(_raw("done"))
    LLMClient(client=api).chat(
        [{"role": "user", "content": "x"}], [{"t": 1}], tool_choice="none"
    )
    assert api.calls[0]["tool_choice"] == "none"


@pytest.mark.parametrize("bad", ["{direction: front", "[1, 2]", "42"])
def test_malformed_arguments_are_kept_not_raised(bad: str) -> None:
    api = _fake_api(_raw(None, [_tool_call("read_lidar", bad)]))
    resp = LLMClient(client=api).chat([{"role": "user", "content": "x"}])
    assert resp.tool_calls[0].arguments == {}
    assert resp.tool_calls[0].arguments_error is not None


def test_empty_arguments_mean_no_arguments() -> None:
    api = _fake_api(_raw(None, [_tool_call("read_lidar", "")]))
    resp = LLMClient(client=api).chat([{"role": "user", "content": "x"}])
    assert (
        resp.tool_calls[0].arguments == {}
        and resp.tool_calls[0].arguments_error is None
    )


def test_api_failure_becomes_llm_client_error() -> None:
    api = _fake_api(error=TimeoutError("slow"))
    with pytest.raises(LLMClientError, match="slow"):
        LLMClient(client=api).chat([{"role": "user", "content": "x"}])


def test_empty_choices_become_llm_client_error() -> None:
    api = _fake_api(SimpleNamespace(choices=[]))
    with pytest.raises(LLMClientError, match="no choices"):
        LLMClient(client=api).chat([{"role": "user", "content": "x"}])


def test_missing_api_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMClientError, match="API key"):
        LLMClient()


# ---- repair of a malformed call to a tool that takes no arguments (live T05 failure)
ULTRASONIC = {
    "type": "function",
    "function": {
        "name": "read_ultrasonic",
        "description": "Read the front ultrasonic sensor.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
LIDAR = {
    "type": "function",
    "function": {
        "name": "read_lidar",
        "description": "Read the LiDAR.",
        "parameters": {
            "type": "object",
            "properties": {"direction": {"type": "string"}},
            "required": [],
        },
    },
}


class _ToolFail(Exception):
    status_code = 400

    def __init__(self, generated: str) -> None:
        super().__init__(
            "Error code: 400 - {'error': {'message': 'Failed to parse tool call arguments as "
            "JSON', 'type': 'invalid_request_error', 'code': 'tool_use_failed', "
            f"'failed_generation': '{generated}'}}}}"
        )


def _client_failing_with(
    generated: str, retries: int = 2
) -> tuple[LLMClient, list[Any]]:
    seen: list[Any] = []

    def create(**kwargs: Any) -> Any:
        seen.append(kwargs["temperature"])
        raise _ToolFail(generated)

    api = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    client = LLMClient(
        client=api, temperature=0.0, retry_temperature=0.0, tool_call_retries=retries
    )
    return client, seen


def test_malformed_no_argument_call_is_rebuilt_not_retried() -> None:
    client, seen = _client_failing_with(
        '{"name": "read_ultrasonic", "arguments": {""}"}'
    )
    reply = client.chat([{"role": "user", "content": "go"}], [ULTRASONIC, LIDAR])
    assert [c.name for c in reply.tool_calls] == ["read_ultrasonic"]
    assert (
        reply.tool_calls[0].arguments == {}
        and reply.tool_calls[0].arguments_error is None
    )
    assert len(seen) == 1  # no pointless identical retries at temperature 0


@pytest.mark.parametrize(
    "generated",
    [
        '{"name": "read_lidar", "arguments": {""}"}',  # tool takes an argument: do not guess
        '{"name": "read_ultrasonic", "arguments": {"direction": "front"}}',  # args present
        '{"name": "move_forward", "arguments": {""}"}',  # tool not offered
        "not a tool call at all",
    ],
)
def test_other_malformed_calls_are_not_rebuilt(generated: str) -> None:
    client, seen = _client_failing_with(generated)
    with pytest.raises(LLMClientError):
        client.chat([{"role": "user", "content": "go"}], [ULTRASONIC, LIDAR])
    assert len(seen) == 3  # first attempt plus the two normal retries
