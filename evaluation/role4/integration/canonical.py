"""Lossless canonical boundaries with explicit, display-only Role 4 projections."""
from datetime import datetime, timezone

from contracts.models import Belief, SensorReading, ToolResult
from evaluation.role4.models import BeliefState

SUBJECTS = {"path_a": "path_A", "box": "box_01", "path_c": "path_A"}


def canonical_timestamp(value):
    """Translate an aware reference ISO timestamp to canonical UTC Z; reject naive dates."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Reference timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def belief_view(payload):
    """Keep canonical validity/history intact alongside a reference display projection."""
    belief = Belief.model_validate(payload)
    projection = BeliefState(
        belief.belief_id, belief.subject, belief.predicate, belief.object,
        belief.perspective, belief.source, belief.confidence, belief.timestamp,
    )
    return {"canonical": belief.model_dump(mode="json"), "reference_view": projection.to_dict()}


class CanonicalMemoryAdapter:
    """Wrap an injected actual memory; never send reference IDs/fields into its tools."""
    def __init__(self, memory):
        self.memory = memory
        self.aliases = {}

    def seed_reference(self, belief):
        receipt = ToolResult.model_validate(self.memory.add_belief(
            subject=SUBJECTS[belief.subject], predicate=belief.predicate,
            object=belief.value, source=belief.source, confidence=float(belief.confidence),
            perspective=belief.perspective, timestamp=canonical_timestamp(belief.observed_at),
        )).model_dump(mode="json")
        if not receipt["ok"]:
            raise ValueError(receipt["error"])
        self.aliases[belief.belief_id] = receipt["data"]["belief_id"]
        return receipt

    def snapshot(self):
        state = self.memory.snapshot()
        for belief in state["nodes"]:
            Belief.model_validate(belief)
        return state


def sensor_evidence(envelope):
    """Validate the official envelope/reading before calling Asvin's existing adapter."""
    from adapters.sensor_to_belief import reading_to_evidence
    result = ToolResult.model_validate(envelope)
    if not result.ok:
        return None
    reading = SensorReading.model_validate(result.data)
    evidence = reading_to_evidence(reading)
    return None if evidence is None else evidence.as_dict()
