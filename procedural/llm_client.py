"""LLM client: thin wrapper over a hosted OpenAI-compatible chat API (default Groq, 8B).

The agent only sees `LLMBackend.chat`, so the scripted fake LLM and a future local
model plug in without touching the loop. Temperature defaults to 0 (Guidelines 6).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

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
    arguments_error: Optional[str] = None


@dataclass
class LLMResponse:
    """Normalised model reply: free text and/or tool calls."""

    content: Optional[str]
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


class LLMBackend(Protocol):
    """Anything the agent can talk to: real client or scripted fake."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResponse: ...


class LLMClient:
    """Chat client for an OpenAI-compatible endpoint.

    Inputs: messages (OpenAI format), optional tool schemas. Output: LLMResponse.
    Raises LLMClientError on a missing key or API failure.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,  # gpt-oss spends tokens on hidden reasoning first
        timeout: float = 30.0,
        client: Any = None,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens = max_tokens
        if client is not None:  # injected (tests)
            self._client = client
            return
        key = api_key or os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
        if not key:
            raise LLMClientError("No API key: set GROQ_API_KEY (or LLM_API_KEY) in .env")
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
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResponse:
        """Send one chat turn and return the normalised response.

        Inputs: messages, optional tool schemas, optional tool_choice ("auto" by default
        when tools are given; "none" forces a plain-text answer). Output: LLMResponse.
        Raises LLMClientError on API failure or an empty reply.
        """
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        try:
            raw = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # transport/API errors; rate-limit policy comes in week 8
            logger.error("LLM request failed: %s", exc)
            hint = ""
            if "model_not_found" in str(exc):
                hint = " Run `python -m scripts.list_available_models` and set LLM_MODEL in .env."
            raise LLMClientError(f"LLM request failed: {exc}{hint}") from exc
        if not raw.choices:
            raise LLMClientError("LLM returned no choices")
        choice = raw.choices[0]
        calls = [_parse_tool_call(tc) for tc in (choice.message.tool_calls or [])]
        return LLMResponse(
            content=choice.message.content,
            tool_calls=calls,
            finish_reason=choice.finish_reason,
        )


def _parse_tool_call(tc: Any) -> ToolCall:
    """Parse arguments JSON; keep the error instead of raising so the loop can repair it."""
    raw_args = tc.function.arguments or "{}"
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        return ToolCall(id=tc.id, name=tc.function.name, arguments=args)
    except ValueError as exc:
        logger.warning("Malformed tool arguments for %s: %s", tc.function.name, exc)
        return ToolCall(id=tc.id, name=tc.function.name, arguments={}, arguments_error=str(exc))
