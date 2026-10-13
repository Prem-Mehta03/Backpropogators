"""Provenance guard for memory writes (a rule in code: the LLM never invents evidence).

Checks the model's downgrade_belief and update_belief calls against what actually happened in
this run, before they reach the memory layer:
- downgrade_belief: the belief id must have been returned by a memory tool earlier in this run
  (no invented ids), the belief must not be a user or third_party view (those are reported,
  never downgraded), and the new confidence is set by rule: DOWNGRADE_FACTOR times the old one.
- update_belief from the person (perspective user, source user): confidence is fixed at
  USER_INPUT_CONFIDENCE.
- update_belief (any perspective): the subject must be an entity seen in this run (a known
  entity id, named in the question, or returned by an earlier memory or sensor result), so a
  mistyped id such as box_1 cannot create a stray belief.
- update_belief with perspective agent_sensor: the source must be a sensor that was read
  successfully in this run, and the confidence is taken from that reading, not from the model.
Everything else passes through to the normal argument validation unchanged. This module holds
no conflict-priority rules; those belong to declarative/conflicts.py.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from procedural.state import MEMORY_TOOLS

SENSOR_READ_TOOLS = ("read_lidar", "read_camera", "get_position")

# A downgraded belief keeps FACTOR times its old confidence (rounded to 2 decimals). Why 0.3:
# - below 0.5: Guidelines section 5 calls a reading under 0.5 "weak", so a downgraded belief
#   must fall under that line even from 1.0, or it would still compete with the live reading;
# - above 0.1 for any belief that was still credible (0.4 or more), so the old record stays
#   visible in the graph and is not mistaken for a deleted one (0.4 * 0.3 = 0.12);
# - the band left by those two limits is 0.25 up to (not including) 0.5, and 0.3 sits at its
#   low end, so a strongly held belief (1.0) lands at 0.3 and a weaker one (0.8) at 0.24.
# The 0.5 limit comes from the Guidelines; the 0.1 visibility floor and the exact 0.3 are our
# own design choice. The model's own number is replaced, so logs are the same on every run.
DOWNGRADE_FACTOR = 0.3
# A person's own statement is a user-perspective belief: fixed at the confidence the demo data
# gives user statements. It is never promoted to a verified fact (Guidelines section 5).
USER_INPUT_CONFIDENCE = 0.9
# Beliefs that are someone's view, not a fact a sensor can overrule: report them, never downgrade.
VIEW_PERSPECTIVES = ("user", "third_party")


@dataclass(frozen=True)
class GuardDecision:
    """Outcome of a check: the arguments to run, or an error message to show the model."""

    args: dict[str, Any]
    error: str | None = None
    overridden: dict[str, Any] = field(default_factory=dict)


def _belief_items(data: Any) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    return [i for i in items if isinstance(i, dict) and "belief_id" in i]


def known_belief_perspectives(tool_log: list[dict[str, Any]]) -> dict[str, str]:
    """Belief id -> perspective, from successful memory results in this run."""
    known: dict[str, str] = {}
    for entry in tool_log:
        result = entry["result"]
        if entry["tool"] in (*MEMORY_TOOLS, "downgrade_belief") and result["ok"]:
            for belief in _belief_items(result["data"]):
                if isinstance(belief.get("perspective"), str):
                    known[belief["belief_id"]] = belief["perspective"]
    return known


def known_belief_confidences(tool_log: list[dict[str, Any]]) -> dict[str, float]:
    """Belief id -> latest confidence, from successful memory results in this run."""
    known: dict[str, float] = {}
    for entry in tool_log:
        result = entry["result"]
        if entry["tool"] in (*MEMORY_TOOLS, "downgrade_belief") and result["ok"]:
            for belief in _belief_items(result["data"]):
                known[belief["belief_id"]] = belief["confidence"]
    return known


def sensor_readings(tool_log: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sensor name -> most recent successful reading in this run."""
    readings: dict[str, dict[str, Any]] = {}
    for entry in tool_log:
        result = entry["result"]
        if (
            entry["tool"] in SENSOR_READ_TOOLS
            and result["ok"]
            and isinstance(result["data"], dict)
        ):
            readings[result["data"]["sensor"]] = result["data"]
    return readings


def seen_subjects(tool_log: list[dict[str, Any]]) -> set[str]:
    """Entity ids seen in this run's results: belief subjects and camera object ids."""
    seen: set[str] = set()
    for entry in tool_log:
        result = entry["result"]
        if not result["ok"]:
            continue
        for belief in _belief_items(result["data"]):
            if isinstance(belief.get("subject"), str):
                seen.add(belief["subject"])
        data = result["data"]
        value = data.get("value") if isinstance(data, dict) else None
        if isinstance(value, dict) and isinstance(value.get("object_id"), str):
            seen.add(value["object_id"])
    return seen


def _check_subject(
    args: dict[str, Any],
    tool_log: list[dict[str, Any]],
    known_subjects: Collection[str],
    question: str,
) -> GuardDecision | None:
    """Refuse a write about an entity this run has not seen; None when the subject is fine."""
    subject = args.get("subject")
    if not isinstance(subject, str):
        return None  # malformed: normal validation reports it
    if subject in known_subjects or subject in seen_subjects(tool_log):
        return None
    if subject.lower() in question.lower():
        return None
    choices = sorted({*known_subjects, *seen_subjects(tool_log)})
    return GuardDecision(
        args,
        f"subject {subject!r} is not an entity seen in this run (seen or known: {choices}). "
        "Use the exact entity id from the memory or sensor results; do not retype it.",
    )


def _check_downgrade(
    args: dict[str, Any], tool_log: list[dict[str, Any]]
) -> GuardDecision:
    belief_id, new_confidence = args.get("belief_id"), args.get("new_confidence")
    if not isinstance(belief_id, str) or not isinstance(new_confidence, (int, float)):
        return GuardDecision(args)  # malformed: normal validation reports it
    if isinstance(new_confidence, bool):
        return GuardDecision(args)  # malformed: normal validation reports it
    known = known_belief_confidences(tool_log)
    if belief_id not in known:
        return GuardDecision(
            args,
            f"belief_id {belief_id} was not returned by any memory lookup in this run. "
            "Call query_belief first and use a belief_id from its result.",
        )
    if known_belief_perspectives(tool_log).get(belief_id) in VIEW_PERSPECTIVES:
        return GuardDecision(
            args,
            f"{belief_id} is a {known_belief_perspectives(tool_log)[belief_id]} view, not a "
            "stored fact a sensor can overrule. Do not downgrade it. Report every view and the "
            "live reading, change nothing, and ask the person which one to treat as correct.",
        )
    if new_confidence >= known[belief_id]:
        return GuardDecision(
            args,
            f"new_confidence must be lower than the current confidence {known[belief_id]}.",
        )
    rule_value = round(known[belief_id] * DOWNGRADE_FACTOR, 2)
    if rule_value >= known[belief_id]:
        return GuardDecision(
            args, f"{belief_id} is already at {known[belief_id]}; nothing to lower."
        )
    if new_confidence == rule_value:
        return GuardDecision(args)
    return GuardDecision(
        {**args, "new_confidence": rule_value},
        overridden={
            "new_confidence": {"model_value": new_confidence, "used": rule_value}
        },
    )


def _check_user_input(args: dict[str, Any]) -> GuardDecision:
    """A person's own statement is stored at the fixed user-input confidence."""
    if args.get("confidence") == USER_INPUT_CONFIDENCE:
        return GuardDecision(args)
    return GuardDecision(
        {**args, "confidence": USER_INPUT_CONFIDENCE},
        overridden={
            "confidence": {
                "model_value": args.get("confidence"),
                "used": USER_INPUT_CONFIDENCE,
            }
        },
    )


def _check_sensor_update(
    args: dict[str, Any], tool_log: list[dict[str, Any]]
) -> GuardDecision:
    source = args.get("source")
    if not isinstance(source, str):
        return GuardDecision(args)  # malformed: normal validation reports it
    readings = sensor_readings(tool_log)
    if source not in readings:
        return GuardDecision(
            args,
            f"source {source!r} is not a sensor read successfully in this run "
            f"(sensors read so far: {sorted(readings)}). Read the sensor first and use its name "
            "as the source. You cannot record an observation you have not made.",
        )
    confidence = readings[source]["confidence"]
    if args.get("confidence") == confidence:
        return GuardDecision(args)
    return GuardDecision(
        {**args, "confidence": confidence},
        overridden={
            "confidence": {"model_value": args.get("confidence"), "used": confidence}
        },
    )


def check_memory_call(
    name: str,
    args: dict[str, Any],
    tool_log: list[dict[str, Any]],
    known_subjects: Collection[str] = (),
    question: str = "",
) -> GuardDecision:
    """Check one model-requested call against this run's history.

    Inputs: tool name, the model's arguments, the tool log so far, the known entity ids and the
    question being answered (a write may name an entity that appears in either).
    Output: GuardDecision. `error` set means refuse the call and tell the model why;
    `overridden` lists argument values the code replaced with values taken from evidence.
    """
    if name == "downgrade_belief":
        return _check_downgrade(args, tool_log)
    if name == "update_belief":
        refusal = _check_subject(args, tool_log, known_subjects, question)
        if refusal is not None:
            return refusal
        if args.get("perspective") == "agent_sensor":
            return _check_sensor_update(args, tool_log)
        if args.get("perspective") == "user" and args.get("source") == "user":
            return _check_user_input(args)
    return GuardDecision(args)
