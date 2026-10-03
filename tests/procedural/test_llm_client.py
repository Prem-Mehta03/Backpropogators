"""LLM client: request settings, reply parsing, malformed arguments, failures."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

import pytest

from procedural.llm_client import LLMClient, LLMClientError


def _raw(content: Optional[str], tool_calls: Optional[list] = None) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def _fake_api(raw: Any = None, error: Optional[Exception] = None) -> SimpleNamespace:
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if error:
            raise error
        return raw

    api = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    api.calls = calls  # type: ignore[attr-defined]
    return api


def _tool_call(name: str, args: str) -> SimpleNamespace:
    return SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=args))


def test_plain_reply_is_returned_without_tools_in_request() -> None:
    api = _fake_api(_raw("pong"))
    resp = LLMClient(client=api).chat([{"role": "user", "content": "ping"}])
    assert resp.content == "pong" and resp.tool_calls == []
    assert "tools" not in api.calls[0] and "tool_choice" not in api.calls[0]


def test_temperature_zero_and_tool_call_parsed() -> None:
    api = _fake_api(_raw(None, [_tool_call("read_lidar", '{"direction": "front"}')]))
    resp = LLMClient(client=api).chat([{"role": "user", "content": "x"}], tools=[{"t": 1}])
    assert api.calls[0]["temperature"] == 0.0
    assert api.calls[0]["tool_choice"] == "auto"
    call = resp.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("call_1", "read_lidar", {"direction": "front"})
    assert call.arguments_error is None


def test_tool_choice_none_is_passed_through() -> None:
    api = _fake_api(_raw("done"))
    LLMClient(client=api).chat([{"role": "user", "content": "x"}], [{"t": 1}], tool_choice="none")
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
    assert resp.tool_calls[0].arguments == {} and resp.tool_calls[0].arguments_error is None


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
