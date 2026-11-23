"""Deterministic evidence-priority policies owned by the declarative layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contracts.models import Belief, SensorReading
from contracts.policy import (
    LIVE_SENSOR_MIN,
    MISSING_SOURCE_CAP,
    STALE_AFTER_S,
    STRONG_BELIEF_MIN,
    WEAK_SENSOR_MAX,
)
from contracts.validators import timestamp_value


EVIDENCE_PERSPECTIVES = frozenset({"agent_sensor", "historical"})


@dataclass(frozen=True)
class PriorityDecision:
    """A policy outcome for comparing incoming evidence with a stored belief."""

    action: Literal["accept", "replace", "dispute"]
    reason: str
    confidence: float


def is_stale(belief: Belief, newer: Belief) -> bool:
    """Compare one belief with evidence for the same property using observation time."""
    if (belief.subject, belief.predicate) != (newer.subject, newer.predicate):
        return False
    age = (timestamp_value(newer.timestamp) - timestamp_value(belief.timestamp)).total_seconds()
    return age > STALE_AFTER_S or (age > 0 and belief.perspective == newer.perspective)


def resolve_priority(
    existing: Belief | None,
    incoming: Belief | SensorReading,
    incoming_perspective: str | None = None,
    another_live_sensor_disagrees: bool = False,
) -> PriorityDecision:
    """Apply the evidence-priority rules without relying on prompt text.

    Inputs: existing belief or None, incoming belief/sensor reading, optional
    perspective, and sensor-disagreement flag. Output: accept, replace, or dispute
    with the effective confidence and reason. Errors: none for validated models.
    """
    perspective = incoming_perspective or (
        incoming.perspective if isinstance(incoming, Belief) else "agent_sensor"
    )
    confidence = incoming.confidence
    if isinstance(incoming, Belief) and incoming.source is None:
        confidence = min(confidence, MISSING_SOURCE_CAP)
    if perspective not in EVIDENCE_PERSPECTIVES:
        return PriorityDecision(
            "accept", "attributed viewpoints coexist with evidence", confidence
        )
    if another_live_sensor_disagrees:
        return PriorityDecision(
            "dispute", "live sensors disagree; request more evidence", confidence
        )
    if existing is None or existing.perspective not in EVIDENCE_PERSPECTIVES:
        return PriorityDecision(
            "accept", "no prior belief competes with this evidence", confidence
        )

    is_live_sensor = (
        isinstance(incoming, SensorReading) or perspective == "agent_sensor"
    )
    incoming_value = incoming.object if isinstance(incoming, Belief) else incoming.value
    if isinstance(incoming, SensorReading) and incoming.unit == "cm" and existing.predicate == "status":
        incoming_value = incoming.status
    values_disagree = incoming_value != existing.object
    evidence_time = timestamp_value(incoming.timestamp)
    existing_time = timestamp_value(existing.timestamp)
    existing_start = timestamp_value(existing.valid_from)
    if values_disagree and is_live_sensor:
        if confidence < WEAK_SENSOR_MAX and existing.confidence >= STRONG_BELIEF_MIN:
            return PriorityDecision(
                "dispute",
                "low-confidence sensor cannot replace a strong belief",
                confidence,
            )
        if (
            confidence >= LIVE_SENSOR_MIN
            and existing.perspective == "historical"
            and evidence_time > existing_time
            and evidence_time >= existing_start
        ):
            return PriorityDecision(
                "replace",
                "current sensor evidence outranks older historical belief",
                confidence,
            )
    if perspective == existing.perspective:
        if evidence_time > existing_time and evidence_time >= existing_start:
            return PriorityDecision(
                "replace",
                "newer evidence from the same perspective takes priority",
                confidence,
            )
        return PriorityDecision(
            "dispute",
            "same-perspective evidence is not newer than the stored belief",
            confidence,
        )
    if not values_disagree:
        return PriorityDecision(
            "accept", "the claims agree and their perspectives are retained", confidence
        )
    return PriorityDecision(
        "dispute",
        "evidence priority is unresolved; retain both perspectives",
        confidence,
    )


def find_conflicts(beliefs: list[Belief]) -> list[Belief]:
    """Return current claims that disagree on an identical subject and predicate.

    Input: Belief objects for one subject/predicate. Output: conflicting active or
    disputed beliefs, or an empty list when there is at most one distinct value.
    Errors: none for validated models.
    """
    current = [
        belief for belief in beliefs
        if belief.status in ("active", "disputed")
        and belief.perspective in EVIDENCE_PERSPECTIVES
    ]
    values = {repr(belief.object) for belief in current}
    if len(values) <= 1:
        return []
    return current
