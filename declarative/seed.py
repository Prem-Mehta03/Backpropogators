"""Explicit fixture helpers for deterministic memory setup."""

from __future__ import annotations

from typing import Any

from contracts.models import BeliefValue

from .belief_graph import BeliefMemory


def seed_bot_02_record(
    memory: BeliefMemory,
    subject: str,
    predicate: str,
    object_value: BeliefValue,
    confidence: float,
    timestamp: str,
) -> dict[str, Any]:
    """Seed a caller-supplied third-party claim attributed to bot_02."""
    return memory.add_belief(
        subject=subject,
        predicate=predicate,
        object=object_value,
        source="bot_02",
        confidence=confidence,
        perspective="third_party",
        timestamp=timestamp,
    )
