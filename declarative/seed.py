"""Explicit fixture helpers for deterministic memory setup."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from contracts.models import BeliefValue
from contracts.policy import USER_STATEMENT_CONF
from contracts.validators import timestamp_value

from .belief_graph import BeliefMemory

SCENARIO_TEST_IDS = {
    "scenario_a": "T01",
    "scenario_map_blocked": "T02",
    "scenario_b": "T03",
    "scenario_b_approach": "T03",
    "scenario_t04_low_confidence": "T04",
    "scenario_t05_sensor_disagreement": "T05",
    "scenario_t06_stale_map": "T06",
    "scenario_t09_missing_provenance": "T09",
    "scenario_t10_world_change": "T10",
}


def seed_for(scenario_id: str, memory: BeliefMemory) -> list[dict[str, Any]]:
    """Create the agreed starting beliefs in an empty memory and return their receipts.

    Accept a T01–T10 ID or its named scenario. Raise ValueError for an unsupported
    ID, nonempty memory, or unsuccessful seed write. The caller owns cleanup.
    """
    test_id = SCENARIO_TEST_IDS.get(scenario_id, scenario_id.upper())
    if test_id not in {f"T{number:02}" for number in range(1, 11)}:
        raise ValueError(f"Unknown evaluation seed: {scenario_id}")
    if memory.snapshot()["nodes"]:
        raise ValueError("Scenario seeds require fresh memory")
    clock = timestamp_value(memory.now())
    before = (clock - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")

    if test_id == "T03":
        receipts = [
            memory.add_belief("box_01", "color", "red", "user", USER_STATEMENT_CONF, "user", before),
            seed_bot_02_record(memory, "box_01", "color", "blue", 0.8, before),
        ]
    elif test_id == "T06":
        previous = "2026-09-01T09:00:00Z"
        revised = (clock - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        if timestamp_value(revised) <= timestamp_value(previous):
            raise ValueError("T06 simulated clock must follow the revised floor-plan timestamp")
        receipts = [
            memory.add_belief("path_A", "status", "blocked", "default_map", 1.0, "historical", previous),
            memory.update_belief("path_A", "status", "clear", "floor_plan_rev2", 0.9,
                                 "historical", "revised historical floor plan", revised),
        ]
    elif test_id in {"T07", "T08"}:
        # T07 has no data for box_99. T08 records its attributed user claim during the run.
        receipts = []
    else:
        value = "blocked" if test_id == "T02" else "clear"
        source = None if test_id == "T09" else "default_map"
        confidence = 0.9 if test_id == "T09" else 1.0
        receipts = [
            memory.add_belief("path_A", "status", value, source, confidence, "historical", before),
        ]
    if not all(receipt["ok"] for receipt in receipts):
        raise ValueError(f"Unable to seed {test_id}: {receipts}")
    return receipts


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
