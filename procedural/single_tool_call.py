"""One question, one tool round: the smallest proof that the model can use a tool.

This is NOT the ReAct loop (that is agent.py). It makes exactly two model calls:
1. the model sees the question and the tool list, and may ask for a tool;
2. the model sees the tool result and must answer in plain text.

agent.py will replace it with a loop that has a step limit and the evidence checklist.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from procedural.llm_client import LLMBackend, ToolCall
from procedural.prompts import SYSTEM_PROMPT
from procedural.tools import TOOL_SCHEMAS, ToolFn, call_tool, error_result

logger = logging.getLogger(__name__)


@dataclass
class SingleToolCallResult:
    """What happened: the logged tool calls, the final answer and the full message list."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_was_called(self) -> bool:
        """True if the model asked for at least one tool."""
        return bool(self.tool_calls)


def _assistant_message(content: str | None, calls: list[ToolCall]) -> dict[str, Any]:
    """Rebuild the assistant turn exactly as the API expects it back in the history."""
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in calls
        ],
    }


def run_single_tool_call(
    llm: LLMBackend, question: str, registry: dict[str, ToolFn]
) -> SingleToolCallResult:
    """Run one question through at most one tool round.

    Inputs: an LLM backend (real or scripted), the question, a registry of tool functions.
    Output: SingleToolCallResult. If the model never asks for a tool, tool_calls is empty
    and the caller can see that (we do not hide a skipped tool). Malformed arguments from
    the model are turned into an INVALID_ARGUMENT envelope that the model then sees.
    Raises LLMClientError (from the backend) if the API fails.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    result = SingleToolCallResult(messages=messages)

    first = llm.chat(messages, TOOL_SCHEMAS)
    if not first.tool_calls:
        logger.warning("Model answered without calling any tool")
        result.answer = first.content or ""
        return result

    messages.append(_assistant_message(first.content, first.tool_calls))
    for step, call in enumerate(first.tool_calls, start=1):
        if call.arguments_error is not None:
            envelope = error_result(
                call.name, "INVALID_ARGUMENT", f"Malformed arguments: {call.arguments_error}"
            )
        else:
            envelope = call_tool(call.name, call.arguments, registry)
        logger.info("step=%d tool=%s ok=%s", step, call.name, envelope["ok"])
        result.tool_calls.append(
            {"step": step, "tool": call.name, "args": call.arguments, "result": envelope}
        )
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(envelope)})

    final = llm.chat(messages, TOOL_SCHEMAS, tool_choice="none")
    result.answer = final.content or ""
    return result
