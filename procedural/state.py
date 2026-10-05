"""Agent state: the notebook the loop keeps, because the model itself remembers nothing.

One AgentState exists per question and is created by new_agent_state (no global state,
Guidelines 6). It holds the conversation, a log of every tool call in the test-log format
(Guidelines 4.6) and counters the loop uses for the step limit.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from procedural.llm_client import ToolCall

MEMORY_TOOLS = (
    "query_belief",
    "get_belief_history",
    "detect_conflict",
    "update_belief",
)


@dataclass
class AgentState:
    """Everything the agent knows about one run."""

    question: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    evidence_nudges: int = 0

    def add_assistant_turn(self, content: str | None, calls: list[ToolCall]) -> None:
        """Append the model's turn exactly as the API expects it back in the history."""
        message: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in calls
            ]
        self.messages.append(message)

    def add_tool_result(
        self,
        call: ToolCall,
        envelope: dict[str, Any],
        args: dict[str, Any] | None = None,
        guard: dict[str, Any] | None = None,
    ) -> None:
        """Log one executed tool call and append its result for the model to read.

        `args` are the arguments that actually ran (they differ from the model's when the
        provenance guard replaced a value); `guard` records what the guard refused or replaced.
        """
        entry: dict[str, Any] = {
            "step": len(self.tool_log) + 1,
            "tool": call.name,
            "args": call.arguments if args is None else args,
            "result": envelope,
        }
        if guard:
            entry["guard"] = guard
        self.tool_log.append(entry)
        self.messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": json.dumps(envelope)}
        )

    def add_user_note(self, text: str) -> None:
        """Append a short instruction from the harness (not from the person asking)."""
        self.messages.append({"role": "user", "content": text})

    def tools_called(self) -> list[str]:
        """Names of tools called so far, in order."""
        return [entry["tool"] for entry in self.tool_log]

    def has_evidence_from(self, tool: str) -> bool:
        """True if `tool` was called and returned ok with data (not an error or empty list)."""
        for entry in self.tool_log:
            result = entry["result"]
            if (
                entry["tool"] == tool
                and result["ok"]
                and result["data"] not in (None, [], {})
            ):
                return True
        return False


def subjects_outside(
    tool_calls: list[dict[str, Any]], known_subjects: Collection[str]
) -> list[str]:
    """Subjects used in memory tool calls that are not in the known entity list.

    Inputs: a tool log (state.tool_log or AgentResult.tool_calls) and the allowed ids.
    Output: the offending subjects in call order, repeats included; [] if all were known.
    """
    return [
        str(entry["args"]["subject"])
        for entry in tool_calls
        if entry["tool"] in MEMORY_TOOLS
        and "subject" in entry["args"]
        and entry["args"]["subject"] not in known_subjects
    ]


def new_agent_state(question: str, system_prompt: str) -> AgentState:
    """Create a fresh state for one question.

    Inputs: the question and the system prompt text. Output: an AgentState whose message
    list already holds the system and user messages.
    """
    state = AgentState(question=question)
    state.messages.append({"role": "system", "content": system_prompt})
    state.messages.append({"role": "user", "content": question})
    return state
