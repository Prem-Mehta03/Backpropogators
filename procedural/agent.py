"""The ReAct loop: ask the model, run the tools it asks for, repeat until it answers.

run_agent is the procedural layer's one public entry point. It never raises for model or
tool problems: failures come back inside AgentResult.error using the fixed error codes
(Guidelines 4.4), so a test harness can always log what happened.

Two rules are enforced here in code, not left to the prompt (Guidelines 2 and 5):
- the evidence checklist: a final answer is refused until memory and a sensor were consulted;
- the provenance guard: memory writes must be backed by evidence gathered in this run;
- the claim check: an answer may not claim a memory write the tool log does not show, and
  must name every belief the run really wrote. The model gets MAX_CLAIM_REFUSALS retries; after
  that the answer is a plain summary built from the tool log (answer_source "fallback_summary").
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from contracts.policy import MAX_CLAIM_REFUSALS, MAX_MODEL_CALLS
from procedural.answer_text import normalize_answer_text
from procedural.checklist import (
    DEFAULT_REQUIRED_EVIDENCE,
    EvidenceCapability,
    capability_evidence,
    missing_evidence,
)
from procedural.claims import unbacked_write_claims
from procedural.fallback_summary import build_fallback_summary
from procedural.llm_client import LLMBackend, LLMClientError, LLMResponse, ToolCall
from procedural.prompts import (
    ABSTENTION_SIGNAL,
    MISSING_REPLY_NOTE,
    build_capability_abstention_note,
    build_checklist_note,
    build_claim_note,
    build_system_prompt,
)
from procedural.recheck import recheck_before_action
from procedural.state import MEMORY_TOOLS, AgentState, new_agent_state
from procedural.tools import (
    SPECS_BY_NAME,
    TOOL_SCHEMAS,
    ToolFn,
    call_tool,
    error_result,
    registered_tool_schemas,
    validate_arguments,
)
from procedural.update_guard import check_memory_call

logger = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = MAX_MODEL_CALLS
ANSWER_FROM_MODEL = "llm"
ANSWER_FROM_FALLBACK = "fallback_summary"


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
    claim_nudges: int = 0
    answer_source: str = ANSWER_FROM_MODEL
    claim_refusals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        """True if the run ended with a final answer rather than an error."""
        return self.error is None


def next_step(
    state: AgentState, llm: LLMBackend, tool_schemas: list[dict[str, Any]] | None = None
) -> LLMResponse:
    """Make one model call using the whole conversation so far.

    Inputs: the agent state and an LLM backend. Output: the model's reply.
    Raises LLMClientError (from the backend) if the API fails.
    """
    state.model_calls += 1
    return llm.chat(
        state.messages, TOOL_SCHEMAS if tool_schemas is None else tool_schemas
    )


# Called after every tool call, including calls the guard refused and the LiDAR read the
# recheck makes before a move (auto=True): (step, tool, args, result, auto). `step` counts these
# events from 1. It carries tool data only; the procedural layer never sees the environment.
StepCallback = Callable[[int, str, dict[str, Any], dict[str, Any], bool], None]
Notifier = Callable[[str, dict[str, Any], dict[str, Any], bool], None]


def make_notifier(on_step: StepCallback | None) -> Notifier:
    """Wrap the optional on_step callback: number the events, hand over copies, never raise.

    An observer (the 3-D view, a frame recorder) must not be able to break a run, so an
    exception in the callback is logged and the run carries on.
    """
    counter = {"events": 0}

    def notify(
        tool: str, args: dict[str, Any], result: dict[str, Any], auto: bool
    ) -> None:
        counter["events"] += 1
        if on_step is None:
            return
        try:
            on_step(
                counter["events"],
                tool,
                copy.deepcopy(args),
                copy.deepcopy(result),
                auto,
            )
        except Exception:  # the observer must never stop the agent
            logger.exception("on_step callback failed; the run continues")

    return notify


@dataclass
class ToolOutcome:
    """Result of executing one tool call: what the model sees and what actually ran."""

    envelope: dict[str, Any]
    args: dict[str, Any]
    guard: dict[str, Any] | None = None
    before: list[dict[str, Any]] = field(
        default_factory=list
    )  # log entries the code made


def execute_tool_call(
    call: ToolCall,
    registry: dict[str, ToolFn],
    tool_log: list[dict[str, Any]],
    known_subjects: Collection[str] = (),
    question: str = "",
    notify: Notifier | None = None,
) -> ToolOutcome:
    """Run one model-requested tool call and return its ToolResult envelope.

    `notify`, when given, is told about the recheck's LiDAR read at the moment it happens
    (before the move runs), so an observer sees the world as the recheck saw it.

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
    spec = SPECS_BY_NAME.get(call.name)
    if spec is not None:
        try:
            validate_arguments(spec, call.arguments)
        except ValueError as exc:
            return ToolOutcome(
                error_result(call.name, "INVALID_ARGUMENT", str(exc)), call.arguments
            )
    decision = check_memory_call(
        call.name,
        call.arguments,
        tool_log,
        known_subjects,
        question,
        requires_ultrasonic="read_ultrasonic" in registry,
    )
    if decision.error is not None:
        envelope = error_result(call.name, "INVALID_ARGUMENT", decision.error)
        return ToolOutcome(envelope, call.arguments, {"refused": decision.error})
    guard: dict[str, Any] = {}
    if decision.overridden:
        guard["overridden"] = decision.overridden

    def notify_read(name: str, args: dict[str, Any], envelope: dict[str, Any]) -> None:
        if notify is not None:
            notify(name, args, envelope, True)

    check = recheck_before_action(call.name, decision.args, registry, notify_read)
    if check is not None:
        guard["recheck"] = check.details
        if check.cancel is not None:
            envelope = error_result(call.name, "CONFLICT", check.cancel)
            return ToolOutcome(envelope, decision.args, guard)
    envelope = call_tool(call.name, decision.args, registry)
    return ToolOutcome(envelope, decision.args, guard or None)


def build_response(
    state: AgentState,
    answer: str,
    error: dict[str, Any] | None = None,
    answer_normalized: bool = False,
    answer_source: str = ANSWER_FROM_MODEL,
) -> AgentResult:
    """Package the state into an AgentResult.

    Inputs: state, final answer text ("" on failure), optional error dict from error_result,
    whether the answer text was changed by normalize_answer_text, and where the answer came
    from ("llm", or "fallback_summary" when it was built from the tool log).
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
        claim_nudges=state.claim_nudges,
        answer_source=answer_source,
        claim_refusals=state.claim_refusals,
    )


def _fallback(state: AgentState, reason: str) -> AgentResult:
    """End the run with a summary built from the tool log instead of the model's answer."""
    logger.warning("Using the fallback summary: %s", reason)
    summary = build_fallback_summary(state.question, state.tool_log)
    return build_response(state, summary, answer_source=ANSWER_FROM_FALLBACK)


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
    require_written_ids: bool = False,
    on_step: StepCallback | None = None,
    *,
    evidence_capability: EvidenceCapability | None = None,
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
    default needs memory (query_belief) and the registered range sensors for path queries,
    or a sensor for other queries. Pass () to switch the checklist off.
    evidence_capability lets the caller supply the exact subject, property and tool for
    a read-only scoped question, in place of the default checklist. Only the relevant
    read schemas are offered and requests outside that scope are rejected before dispatch.
    For an absent or
    unavailable matching sensor, only an explicit abstention signal is accepted. The
    returned summary is generated from the verified evidence limitation.
    require_written_ids=True also refuses an answer that does not name every belief the run
    wrote (live runs switch this on; scripted test answers need not name ids).
    A premature answer is kept in the history, refused, and the model is told what is missing
    (counted in AgentResult.evidence_nudges). An answer the claim check refuses is sent back at
    most MAX_CLAIM_REFUSALS times (claim_nudges); then the answer is a summary built from the
    tool log, answer_source is "fallback_summary" and every refused text is in claim_refusals.
    on_step is an optional observer called after every tool call as (step, tool, args, result,
    auto); auto is True for automatic range reads before a move. The composition
    root uses it to record 3-D frames. Its exceptions are logged and never stop the run.
    Output: AgentResult.
    Error codes in result.error: STEP_LIMIT (no accepted final answer within max_steps model
    calls; the message names any missing evidence), INTERNAL (the LLM API failed). Tool-level
    errors are not run errors: the model sees them and may recover.
    """
    if (
        evidence_capability is not None
        and required_evidence != DEFAULT_REQUIRED_EVIDENCE
    ):
        raise ValueError(
            "evidence_capability is an alternative to a custom evidence checklist"
        )
    prompt = (
        system_prompt
        if system_prompt is not None
        else build_system_prompt(known_subjects)
    )
    state = new_agent_state(question, prompt)
    notify = make_notifier(on_step)
    tools = (
        registry
        if evidence_capability is None
        else {
            name: fn
            for name, fn in registry.items()
            if name in ("query_belief", evidence_capability.tool)
        }
    )
    tool_schemas = registered_tool_schemas(tools)

    def evidence() -> tuple[list[str], str | None]:
        if evidence_capability is not None:
            return capability_evidence(
                state.tool_log, evidence_capability, tuple(registry)
            )
        return (
            missing_evidence(state.tool_log, required_evidence, tuple(registry)),
            None,
        )

    while state.model_calls < max_steps:
        try:
            reply = next_step(state, llm, tool_schemas)
        except LLMClientError as exc:
            return _failure(state, "INTERNAL", f"LLM call failed: {exc}")

        if reply.tool_calls:
            state.add_assistant_turn(reply.content, reply.tool_calls)
            for call in reply.tool_calls:
                if evidence_capability is not None and not evidence_capability.permits(
                    call.name, call.arguments
                ):
                    reason = "Tool request is outside the read-only evidence scope"
                    outcome = ToolOutcome(
                        error_result(call.name, "INVALID_ARGUMENT", reason),
                        call.arguments,
                        {"refused": reason},
                    )
                else:
                    outcome = execute_tool_call(
                        call,
                        tools,
                        state.tool_log,
                        known_subjects or (),
                        question,
                        notify,
                    )
                logger.info(
                    "model_call=%d tool=%s ok=%s",
                    state.model_calls,
                    call.name,
                    outcome.envelope["ok"],
                )
                state.add_tool_result(
                    call, outcome.envelope, outcome.args, outcome.guard
                )
                notify(call.name, outcome.args, outcome.envelope, False)
                _warn_if_unknown_subject(call, known_subjects)
            continue

        text = (reply.content or "").strip()
        if text:
            state.add_assistant_turn(
                text, []
            )  # the history keeps what the model really said
            missing, abstention = evidence()
            if missing:
                state.evidence_nudges += 1
                logger.warning(
                    "Answer refused, missing evidence: %s", _missing_note(missing)
                )
                state.add_user_note(build_checklist_note(missing))
                continue
            if abstention is not None:
                if text == ABSTENTION_SIGNAL:
                    return build_response(
                        state, abstention, answer_source=ANSWER_FROM_FALLBACK
                    )
                state.evidence_nudges += 1
                state.add_user_note(build_capability_abstention_note())
                logger.warning(
                    "Answer refused: a scoped sensor could not verify the property"
                )
                continue
            unbacked = unbacked_write_claims(text, state.tool_log, require_written_ids)
            if unbacked:
                state.claim_refusals.append(
                    {
                        "attempt": len(state.claim_refusals) + 1,
                        "text": text,
                        "problems": unbacked,
                    }
                )
                if state.claim_nudges >= MAX_CLAIM_REFUSALS:
                    return _fallback(
                        state,
                        f"answer still refused after {MAX_CLAIM_REFUSALS} retries: "
                        + "; ".join(unbacked),
                    )
                state.claim_nudges += 1
                logger.warning(
                    "Answer refused, unbacked claims: %s", "; ".join(unbacked)
                )
                state.add_user_note(build_claim_note(unbacked))
                continue
            clean = normalize_answer_text(text)
            return build_response(state, clean, answer_normalized=clean != text)

        logger.warning("Model returned neither text nor a tool call")
        state.add_user_note(MISSING_REPLY_NOTE)

    message = f"No final answer after {max_steps} model calls"
    missing, abstention = evidence()
    if state.claim_refusals and not missing and abstention is None:
        return _fallback(
            state, f"model calls ran out after {state.claim_nudges} refusals"
        )
    if missing:
        message += f"; required evidence never gathered: {_missing_note(missing)}"
    elif abstention is not None:
        message += "; no accepted abstention for the unavailable capability"
    return _failure(state, "STEP_LIMIT", message)
