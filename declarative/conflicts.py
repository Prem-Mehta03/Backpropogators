"""Deterministic evidence-priority policies owned by the declarative layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contracts.models import Belief, SensorReading


@dataclass(frozen=True)
class PriorityDecision:
    """A policy outcome for comparing incoming evidence with a stored belief."""

    action: Literal["accept", "replace", "dispute"]
    reason: str
    confidence: float


def resolve_priority(
    existing: Belief | None,
    incoming: Belief | SensorReading,
    incoming_perspective: str | None = None,
    another_live_sensor_disagrees: bool = False,
) -> PriorityDecision:
    """Apply the v1.0 evidence-priority rules without relying on prompt text.

    Inputs: existing belief or None, incoming belief/sensor reading, optional
    perspective, and sensor-disagreement flag. Output: accept, replace, or dispute
    with the effective confidence and reason. Errors: none for validated models.
    """
    perspective = incoming_perspective or (
        incoming.perspective if isinstance(incoming, Belief) else "agent_sensor"
    )
    confidence = incoming.confidence
    if isinstance(incoming, Belief) and incoming.source is None:
        confidence = min(confidence, 0.5)
    if another_live_sensor_disagrees:
        return PriorityDecision(
            "dispute", "live sensors disagree; request more evidence", confidence
        )
    if existing is None:
        return PriorityDecision(
            "accept", "no prior belief competes with this evidence", confidence
        )

    is_live_sensor = (
        isinstance(incoming, SensorReading) or perspective == "agent_sensor"
    )
    incoming_value = (
        incoming.value if isinstance(incoming, SensorReading) else incoming.object
    )
    values_disagree = incoming_value != existing.object
    if values_disagree and is_live_sensor:
        if confidence < 0.5 and existing.confidence >= 0.8:
            return PriorityDecision(
                "dispute",
                "low-confidence sensor cannot replace a strong belief",
                confidence,
            )
        if (
            confidence >= 0.6
            and existing.perspective == "historical"
            and incoming.timestamp > existing.timestamp
        ):
            return PriorityDecision(
                "replace",
                "current sensor evidence outranks older historical belief",
                confidence,
            )
    if perspective == existing.perspective:
        if incoming.timestamp > existing.timestamp:
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
    if perspective == "user":
        return PriorityDecision(
            "accept", "user claims remain attributed to the user", confidence
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
    current = [belief for belief in beliefs if belief.status in ("active", "disputed")]
    values = {repr(belief.object) for belief in current}
    if len(values) <= 1:
        return []
    return current
