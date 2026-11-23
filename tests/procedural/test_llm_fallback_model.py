"""D10: LLM_FALLBACK_MODEL. The client switches model for the rest of the run when it must."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from procedural.llm_client import (
    LLMClient,
    LLMClientError,
    is_daily_limit_error,
)

MAIN, BACKUP = "main-model", "backup-model"


class ApiError(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status_code = status


DAILY = ApiError(
    429, "Rate limit reached: tokens per day (TPD): Limit 100000, Used 99990"
)
MINUTE = ApiError(
    429, "Rate limit reached: tokens per minute (TPM). Please try again in 2s"
)
TOOL_FAIL = ApiError(
    400, "tool_use_failed: Failed to parse tool call arguments as JSON"
)


def _ok() -> SimpleNamespace:
    msg = SimpleNamespace(content="pong", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def _api(*outcomes: Any) -> SimpleNamespace:
    """Each outcome is an exception to raise or a reply to return, used in order."""
    queue, calls, temperatures = list(outcomes), [], []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs["model"])
        temperatures.append(kwargs["temperature"])
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    api = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    api.calls = calls  # type: ignore[attr-defined]
    api.temperatures = temperatures  # type: ignore[attr-defined]
    return api


def _client(
    api: Any, fallback: str | None = BACKUP, sleeps: list | None = None
) -> LLMClient:
    return LLMClient(
        model=MAIN,
        fallback_model=fallback,
        client=api,
        rate_limit_retries=2,
        tool_call_retries=1,
        sleep=(sleeps if sleeps is not None else []).append,
    )


MESSAGES = [{"role": "user", "content": "ping"}]


def test_daily_limit_is_recognised_but_a_per_minute_limit_is_not() -> None:
    assert is_daily_limit_error(DAILY)
    assert not is_daily_limit_error(MINUTE)
    assert not is_daily_limit_error(ApiError(500, "tokens per day"))


def test_a_daily_limit_switches_to_the_fallback_without_waiting() -> None:
    api, sleeps = _api(DAILY, _ok()), []
    client = _client(api, sleeps=sleeps)
    assert client.chat(MESSAGES).content == "pong"
    assert api.calls == [MAIN, BACKUP] and sleeps == []
    assert client.model == BACKUP and client.switched_from == MAIN


def test_the_rest_of_the_run_stays_on_the_fallback_model() -> None:
    api = _api(DAILY, _ok(), _ok())
    client = _client(api)
    client.chat(MESSAGES)
    client.chat(MESSAGES)
    assert api.calls == [MAIN, BACKUP, BACKUP]


def test_a_daily_limit_with_no_fallback_stops_at_once_with_a_clear_message() -> None:
    api, sleeps = _api(DAILY), []
    with pytest.raises(LLMClientError, match="Daily limit.*no LLM_FALLBACK_MODEL"):
        _client(api, fallback=None, sleeps=sleeps).chat(MESSAGES)
    assert api.calls == [MAIN] and sleeps == []  # no futile waiting


def test_used_up_rate_limit_retries_switch_to_the_fallback() -> None:
    api, sleeps = _api(MINUTE, MINUTE, MINUTE, _ok()), []
    client = _client(api, sleeps=sleeps)
    assert client.chat(MESSAGES).content == "pong"
    assert api.calls == [MAIN, MAIN, MAIN, BACKUP]
    assert len(sleeps) == 2  # it waited for the main model first, as before


def test_a_short_rate_limit_that_clears_does_not_switch() -> None:
    api = _api(MINUTE, _ok())
    client = _client(api)
    client.chat(MESSAGES)
    assert api.calls == [MAIN, MAIN] and client.switched_from is None


def test_used_up_tool_call_retries_switch_to_the_fallback() -> None:
    api = _api(TOOL_FAIL, TOOL_FAIL, _ok())
    client = _client(api)
    client.chat(MESSAGES)
    assert api.calls == [MAIN, MAIN, BACKUP] and client.switched_from == MAIN


def test_temperature_zero_can_be_pinned_across_retries_and_model_switch() -> None:
    api = _api(TOOL_FAIL, TOOL_FAIL, _ok())
    client = LLMClient(
        model=MAIN, fallback_model=BACKUP, client=api,
        temperature=0.0, retry_temperature=0.0, tool_call_retries=1,
    )
    assert client.chat(MESSAGES).content == "pong"
    assert api.calls == [MAIN, MAIN, BACKUP]
    assert api.temperatures == [0.0, 0.0, 0.0]


def test_there_is_only_one_switch() -> None:
    api = _api(DAILY, DAILY)
    with pytest.raises(LLMClientError, match="Daily limit"):
        _client(api).chat(MESSAGES)
    assert api.calls == [MAIN, BACKUP]


def test_other_errors_do_not_switch_models() -> None:
    api = _api(ApiError(500, "server exploded"))
    client = _client(api)
    with pytest.raises(LLMClientError, match="server exploded"):
        client.chat(MESSAGES)
    assert api.calls == [MAIN] and client.switched_from is None


def test_the_fallback_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "env-backup")
    assert LLMClient(model=MAIN, client=_api()).fallback_model == "env-backup"
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "")
    assert LLMClient(model=MAIN, client=_api()).fallback_model is None
    monkeypatch.delenv("LLM_FALLBACK_MODEL")
    assert LLMClient(model=MAIN, client=_api()).fallback_model is None


def test_a_fresh_client_has_not_switched() -> None:
    assert _client(_api()).switched_from is None
