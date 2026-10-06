"""Scripted fake LLM: replays queued replies and records exactly what it was sent.

Lets us test the agent plumbing with no API key, no network and no randomness. A queued
item may be an LLMResponse or an exception, which is raised when its turn comes.
"""

from __future__ import annotations

from typing import Any

from procedural.llm_client import LLMResponse, ToolCall


class ScriptedLLM:
    """Implements the LLMBackend protocol using a fixed list of replies."""

    def __init__(self, responses: list[LLMResponse | Exception]) -> None:
        self.responses = list(responses)
        self.seen: list[list[dict[str, Any]]] = []
        self.tool_choices: list[str | None] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Record the call and return (or raise) the next scripted item."""
        self.seen.append([dict(m) for m in messages])
        self.tool_choices.append(tool_choice)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def call(name: str, args: dict[str, Any] | None = None, call_id: str = "call_1") -> LLMResponse:
    """A scripted reply asking for one tool."""
    return LLMResponse(None, [ToolCall(call_id, name, args or {})])


def say(text: str) -> LLMResponse:
    """A scripted plain-text reply."""
    return LLMResponse(text)
