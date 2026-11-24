"""LLM client: thin wrapper over a hosted OpenAI-compatible chat API (default Groq, 8B).

The agent only sees `LLMBackend.chat`, so the scripted fake LLM and a future local
model plug in without touching the loop. Temperature defaults to 0 (Guidelines 6).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-20b"  # Groq retired llama-3.1-8b-instant (Aug 2026)


class LLMClientError(RuntimeError):
    """Raised for configuration or transport failures (internal to the procedural layer)."""


@dataclass
class ToolCall:
    """One model-requested tool call. `arguments_error` is set if the JSON was malformed."""

    id: str
    name: str
    arguments: dict[str, Any]
    arguments_error: str | None = None


@dataclass
class LLMResponse:
    """Normalised model reply: free text and/or tool calls."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


class LLMBackend(Protocol):
    """Anything the agent can talk to: real client or scripted fake."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse: ...


RATE_LIMIT_RETRIES = 4
MAX_RATE_LIMIT_WAIT_S = 30.0
TOOL_CALL_RETRIES = 2
RETRY_TEMPERATURE = 0.3


def is_rate_limit_error(exc: Exception) -> bool:
    """True for an HTTP 429 (tokens-per-minute or requests-per-minute limit reached)."""
    return (
        getattr(exc, "status_code", None) == 429
        or type(exc).__name__ == "RateLimitError"
    )


def is_tool_call_generation_error(exc: Exception) -> bool:
    """True when the provider rejected the model's own tool call as malformed (HTTP 400).

    Groq reports this as code `tool_use_failed` ("Failed to parse tool call arguments as JSON").
    It is a model slip, not our request: asking again usually works.
    """
    return getattr(exc, "status_code", None) == 400 and "tool_use_failed" in str(exc)


def is_daily_limit_error(exc: Exception) -> bool:
    """True for a 429 that says the DAILY quota is used up (tokens or requests per day).

    Waiting a few seconds cannot help with this one, so the client does not retry it: it
    switches to the fallback model if one is configured, otherwise it stops with a clear message.
    """
    return is_rate_limit_error(exc) and bool(
        re.search(
            r"per day|tokens per day|requests per day|\bTPD\b|\bRPD\b",
            str(exc),
            re.IGNORECASE,
        )
    )


def rate_limit_wait_seconds(exc: Exception, attempt: int) -> float:
    """How long to wait before retrying a 429.

    Uses the server's own hint ("Please try again in 577.5ms" / "in 2.1s") plus a small margin;
    without a hint it backs off 5 s, 10 s, 15 s... Never more than MAX_RATE_LIMIT_WAIT_S.
    """
    match = re.search(r"try again in ([\d.]+)\s*(ms|s)\b", str(exc))
    if match:
        seconds = float(match.group(1)) / (1000.0 if match.group(2) == "ms" else 1.0)
        return min(seconds + 0.5, MAX_RATE_LIMIT_WAIT_S)
    return min(5.0 * (attempt + 1), MAX_RATE_LIMIT_WAIT_S)


# ---- repair of a malformed call to a tool that takes no arguments (T05 live failure)
FAILED_NAME = re.compile(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"')
FAILED_ARGUMENTS = re.compile(r'"arguments"\s*:(.*)', re.DOTALL)


def _no_argument_tools(tools: list[dict[str, Any]] | None) -> set[str]:
    """Names of the offered tools whose schema has no parameters, such as read_ultrasonic."""
    names: set[str] = set()
    for tool in tools or []:
        function = tool.get("function", {})
        if not function.get("parameters", {}).get("properties"):
            names.add(function.get("name", ""))
    names.discard("")
    return names


def repair_no_argument_call(exc: Exception, tools: list[dict[str, Any]] | None) -> Any | None:
    """Rebuild the one call a provider rejected as malformed when it needs no arguments.

    Groq answers HTTP 400 tool_use_failed when the model writes a tool call such as
    {"name": "read_ultrasonic", "arguments": {""}}: the right tool, garbage in place of an empty
    argument object. Retrying at temperature 0 repeats the same text, so the call is rebuilt
    instead. It is only rebuilt when the named tool is offered, takes no arguments, and the
    rejected text carries no argument key or value at all (nothing is guessed). Returns a
    raw-response-shaped object for LLMClient.chat to parse, or None when the call cannot be
    repaired.
    """
    text = str(exc)
    named = FAILED_NAME.search(text)
    if named is None or named.group(1) not in _no_argument_tools(tools):
        return None
    given = FAILED_ARGUMENTS.search(text[named.end() :])
    leftover = re.sub(r"""[{}"'\s:,]""", "", given.group(1)) if given else ""
    if leftover:
        return None
    call = SimpleNamespace(
        id="repaired_call", function=SimpleNamespace(name=named.group(1), arguments="{}")
    )
    message = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")]
    )


class LLMClient:
    """Chat client for an OpenAI-compatible endpoint.

    Inputs: messages (OpenAI format), optional tool schemas. Output: LLMResponse.
    Raises LLMClientError on a missing key or API failure.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,  # gpt-oss spends tokens on hidden reasoning first
        timeout: float = 30.0,
        fallback_model: str | None = None,
        client: Any = None,
        rate_limit_retries: int = RATE_LIMIT_RETRIES,
        tool_call_retries: int = TOOL_CALL_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        retry_temperature: float = RETRY_TEMPERATURE,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        # LLM_FALLBACK_MODEL (D10): used for the rest of the run only if the main model cannot
        # answer (retries used up, or the daily limit is reached). Empty means no fallback.
        self.fallback_model = (
            fallback_model
            if fallback_model is not None
            else os.getenv("LLM_FALLBACK_MODEL", "")
        ) or None
        self.switched_from: str | None = (
            None  # the main model, once the switch happened
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rate_limit_retries = rate_limit_retries
        self.tool_call_retries = tool_call_retries
        self.retry_temperature = retry_temperature
        self._sleep = sleep
        if client is not None:  # injected (tests)
            self._client = client
            return
        key = api_key or os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
        if not key:
            raise LLMClientError(
                "No API key: set GROQ_API_KEY (or LLM_API_KEY) in .env"
            )
        from openai import OpenAI

        self._client = OpenAI(
            api_key=key,
            base_url=base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
            timeout=timeout,
            max_retries=2,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Send one chat turn and return the normalised response.

        Inputs: messages, optional tool schemas, optional tool_choice ("auto" by default
        when tools are given; "none" forces a plain-text answer). Output: LLMResponse.
        Raises LLMClientError on API failure or an empty reply.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        raw = self._create_with_rate_limit_retries(kwargs)
        if not raw.choices:
            raise LLMClientError("LLM returned no choices")
        choice = raw.choices[0]
        calls = [_parse_tool_call(tc) for tc in (choice.message.tool_calls or [])]
        return LLMResponse(
            content=choice.message.content,
            tool_calls=calls,
            finish_reason=choice.finish_reason,
        )

    def _switch_to_fallback(
        self, kwargs: dict[str, Any], reason: str
    ) -> dict[str, Any] | None:
        """Change to the fallback model for the rest of this client's life; None if impossible.

        Only one switch happens: once on the fallback model there is nothing further to try.
        Returns the request arguments with the new model name.
        """
        if self.fallback_model is None or self.switched_from is not None:
            return None
        logger.warning(
            "Switching from %s to fallback model %s (%s)",
            self.model,
            self.fallback_model,
            reason,
        )
        self.switched_from, self.model = self.model, self.fallback_model
        return {**kwargs, "model": self.model}

    def _create_with_rate_limit_retries(self, kwargs: dict[str, Any]) -> Any:
        """Call the API with two kinds of retry. Raise LLMClientError on any other failure.

        - HTTP 429: wait as the server asks, then retry (up to rate_limit_retries times).
        - HTTP 400 tool_use_failed: the model produced a malformed tool call; retry up to
            tool_call_retries times. The caller can retain temperature zero for measured runs.
        """
        rate_attempts = 0
        tool_attempts = 0
        while True:
            try:
                return self._client.chat.completions.create(**kwargs)
            except Exception as exc:  # transport/API errors
                if is_daily_limit_error(exc):
                    switched = self._switch_to_fallback(kwargs, "daily limit reached")
                    if switched is None:
                        raise LLMClientError(
                            f"Daily limit reached for model {self.model} and no "
                            f"LLM_FALLBACK_MODEL is set: {exc}"
                        ) from exc
                    kwargs, rate_attempts, tool_attempts = switched, 0, 0
                    continue
                if is_rate_limit_error(exc) and rate_attempts < self.rate_limit_retries:
                    wait = rate_limit_wait_seconds(exc, rate_attempts)
                    logger.warning(
                        "Rate limited (attempt %d of %d); waiting %.1f s",
                        rate_attempts + 1,
                        self.rate_limit_retries,
                        wait,
                    )
                    self._sleep(wait)
                    rate_attempts += 1
                    continue
                if is_tool_call_generation_error(exc):
                    repaired = repair_no_argument_call(exc, kwargs.get("tools"))
                    if repaired is not None:
                        logger.warning(
                            "Repaired a malformed call to %s (no arguments needed)",
                            repaired.choices[0].message.tool_calls[0].function.name,
                        )
                        return repaired
                if (
                    is_tool_call_generation_error(exc)
                    and tool_attempts < self.tool_call_retries
                ):
                    tool_attempts += 1
                    logger.warning(
                        "Model produced a malformed tool call (retry %d of %d): %s",
                        tool_attempts,
                        self.tool_call_retries,
                        exc,
                    )
                    kwargs = {
                        **kwargs,
                        "temperature": max(kwargs["temperature"], self.retry_temperature),
                    }
                    continue
                if is_rate_limit_error(exc) or is_tool_call_generation_error(exc):
                    switched = self._switch_to_fallback(kwargs, "retries used up")
                    if switched is not None:
                        kwargs, rate_attempts, tool_attempts = switched, 0, 0
                        continue
                logger.error("LLM request failed: %s", exc)
                hint = ""
                if "model_not_found" in str(exc):
                    hint = (
                        " Run `python -m scripts.list_available_models` "
                        "and set LLM_MODEL in .env."
                    )
                raise LLMClientError(f"LLM request failed: {exc}{hint}") from exc


def _parse_tool_call(tc: Any) -> ToolCall:
    """Parse arguments JSON; keep the error instead of raising so the loop can repair it."""
    raw_args = tc.function.arguments or "{}"
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise TypeError("arguments must be a JSON object")
        return ToolCall(id=tc.id, name=tc.function.name, arguments=args)
    except (TypeError, ValueError) as exc:
        logger.warning("Malformed tool arguments for %s: %s", tc.function.name, exc)
        return ToolCall(
            id=tc.id, name=tc.function.name, arguments={}, arguments_error=str(exc)
        )
