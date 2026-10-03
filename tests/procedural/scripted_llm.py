"""Scripted fake LLM: replays queued responses and records exactly what it was sent.

Lets us test the agent plumbing with no API key, no network and no randomness.
It will grow into the fake used by the integration tests (Guidelines 7 and 8).
"""

from __future__ import annotations

from typing import Any, Optional

from procedural.llm_client import LLMResponse


class ScriptedLLM:
    """Implements the LLMBackend protocol using a fixed list of replies."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.seen: list[list[dict[str, Any]]] = []
        self.tool_choices: list[Optional[str]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResponse:
        """Record the call and return the next scripted response."""
        self.seen.append([dict(m) for m in messages])
        self.tool_choices.append(tool_choice)
        return self.responses.pop(0)
