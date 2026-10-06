"""The ReAct loop: ask the model, run the tools it asks for, repeat until it answers.

run_agent is the procedural layer's one public entry point. It never raises for model or
tool problems: failures come back inside AgentResult.error using the fixed error codes
(Guidelines 4.4), so a test harness can always log what happened.

Two rules are enforced here in code, not left to the prompt (Guidelines 2 and 5):
- the evidence checklist: a final answer is refused until memory and a sensor were consulted;
- the provenance guard: memory writes must be backed by evidence gathered in this run.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from procedural.answer_text import normalize_answer_text
from procedural.checklist import DEFAULT_REQUIRED_EVIDENCE, missing_evidence
from procedural.llm_client import LLMBackend, LLMClientError, LLMResponse, ToolCall
from procedural.prompts import (
    MISSING_REPLY_NOTE,
    build_checklist_note,
    build_system_prompt,
)
from procedural.state import MEMORY_TOOLS, AgentState, new_agent_state
from procedural.tools import TOOL_SCHEMAS, ToolFn, call_tool, error_result
from procedural.update_guard import check_memory_call

logger = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = 10


@dataclass
class AgentResult:
    """Outcome of one run. `error` is None when the model gave a final answer."""

    question: str
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    error: dict[str, Any] | None = None
    answer_normalized: bool = False
    evidence_nudges: int = 0

    @property
    def finished(self) -> bool:
        """True if the run ended with a final answer rather than an error."""
        return self.error is None


def next_step(state: AgentState, llm: LLMBackend) -> LLMResponse:
    """Make one model call using the whole conversation so far.

    Inputs: the agent state and an LLM backend. Output: the model's reply.
    Raises LLMClientError (from the backend) if the API fails.
    """
    state.model_calls += 1
    return llm.chat(state.messages, TOOL_SCHEMAS)


@dataclass
class ToolOutcome:
    """Result of executing one tool call: what the model sees and what actually ran."""

    envelope: dict[str, Any]
    args: dict[str, Any]
    guard: dict[str, Any] | None = None


def execute_tool_call(
    call: ToolCall, registry: dict[str, ToolFn], tool_log: list[dict[str, Any]]
) -> ToolOutcome:
    """Run one model-requested tool call and return its ToolResult envelope.

    Malformed arguments become an INVALID_ARGUMENT envelope the model can read and fix. The
    provenance guard may refuse a memory write (INVALID_ARGUMENT with the reason) or replace
    argument values with values taken from this run's evidence; both are recorded in `guard`.
    """
    if call.arguments_error is not None:
        envelope = error_result(
            call.name,
            "INVALID_ARGUMENT",
            f"Malformed arguments: {call.arguments_error}",
        )
        return ToolOutcome(envelope, call.arguments)
    decision = check_memory_call(call.name, call.arguments, tool_log)
    if decision.error is not None:
        envelope = error_result(call.name, "INVALID_ARGUMENT", decision.error)
        return ToolOutcome(envelope, call.arguments, {"refused": decision.error})
    envelope = call_tool(call.name, decision.args, registry)
    guard = {"overridden": decision.overridden} if decision.overridden else None
    return ToolOutcome(envelope, decision.args, guard)


def build_response(
    state: AgentState,
    answer: str,
    error: dict[str, Any] | None = None,
    answer_normalized: bool = False,
) -> AgentResult:
    """Package the state into an AgentResult.

    Inputs: state, final answer text ("" on failure), optional error dict from error_result,
    and whether the answer text was changed by normalize_answer_text.
    """
    return AgentResult(
        question=state.question,
        answer=answer,
        tool_calls=state.tool_log,
        messages=state.messages,
        model_calls=state.model_calls,
        error=error,
        answer_normalized=answer_normalized,
        evidence_nudges=state.evidence_nudges,
    )


def _failure(state: AgentState, code: str, message: str) -> AgentResult:
    logger.warning("Run stopped: %s: %s", code, message)
    error = error_result("agent", code, message)["error"]
    return build_response(state, "", error)


def _warn_if_unknown_subject(
    call: ToolCall, known_subjects: Mapping[str, str] | None
) -> None:
    """Log a warning when a memory tool is called with a subject outside the entity list."""
    if not known_subjects or call.name not in MEMORY_TOOLS:
        return
    subject = call.arguments.get("subject")
    if subject is not None and subject not in known_subjects:
        logger.warning(
            "%s called with unknown subject %r (known: %s)",
            call.name,
            subject,
            sorted(known_subjects),
        )


def _missing_note(missing: Sequence[str]) -> str:
    return "; ".join(missing)


def run_agent(
    question: str,
    llm: LLMBackend,
    registry: dict[str, ToolFn],
    max_steps: int = DEFAULT_MAX_STEPS,
    system_prompt: str | None = None,
    known_subjects: Mapping[str, str] | None = None,
    required_evidence: Sequence[tuple[str, ...]] = DEFAULT_REQUIRED_EVIDENCE,
) -> AgentResult:
    """Answer a question by letting the model call tools, with a hard step limit.

    Inputs: the question, an LLM backend (real or scripted), a registry of tool functions
    (name -> function from the other layers), the maximum number of model calls, an optional
    full system prompt (default: the standard prompt) and known_subjects, a mapping of entity
    id -> description from the runner or scenario config. When given, the ids are listed in
    the prompt, and a memory call with any other subject is logged as a warning (it is not
    blocked: tests 7 and 8 legitimately involve unknown entities).
    required_evidence is the checklist: each entry is a group of tool names, and at least one
    tool of every group must have been attempted before a final answer is accepted. The
    default needs memory (query_belief) and a sensor. Pass () to switch the checklist off.
    A premature answer is kept in the history, refused, and the model is told what is missing
    (counted in AgentResult.evidence_nudges). Output: AgentResult.
    Error codes in result.error: STEP_LIMIT (no accepted final answer within max_steps model
    calls; the message names any missing evidence), INTERNAL (the LLM API failed). Tool-level
    errors are not run errors: the model sees them and may recover.
    """
    prompt = (
        system_prompt
        if system_prompt is not None
        else build_system_prompt(known_subjects)
    )
    state = new_agent_state(question, prompt)
    while state.model_calls < max_steps:
        try:
            reply = next_step(state, llm)
        except LLMClientError as exc:
            return _failure(state, "INTERNAL", f"LLM call failed: {exc}")

        if reply.tool_calls:
            state.add_assistant_turn(reply.content, reply.tool_calls)
            for call in reply.tool_calls:
                outcome = execute_tool_call(call, registry, state.tool_log)
                logger.info(
                    "model_call=%d tool=%s ok=%s",
                    state.model_calls,
                    call.name,
                    outcome.envelope["ok"],
                )
                state.add_tool_result(
                    call, outcome.envelope, outcome.args, outcome.guard
                )
                _warn_if_unknown_subject(call, known_subjects)
            continue

        text = (reply.content or "").strip()
        if text:
            state.add_assistant_turn(
                text, []
            )  # the history keeps what the model really said
            missing = missing_evidence(state.tool_log, required_evidence)
            if missing:
                state.evidence_nudges += 1
                logger.warning(
                    "Answer refused, missing evidence: %s", _missing_note(missing)
                )
                state.add_user_note(build_checklist_note(missing))
                continue
            clean = normalize_answer_text(text)
            return build_response(state, clean, answer_normalized=clean != text)

        logger.warning("Model returned neither text nor a tool call")
        state.add_user_note(MISSING_REPLY_NOTE)

    message = f"No final answer after {max_steps} model calls"
    missing = missing_evidence(state.tool_log, required_evidence)
    if missing:
        message += f"; required evidence never gathered: {_missing_note(missing)}"
    return _failure(state, "STEP_LIMIT", message)
