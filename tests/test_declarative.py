"""Tests for persistent belief history and evidence conflict rules."""

from __future__ import annotations

import sqlite3

import pytest

from contracts.models import Belief, SensorReading
from declarative import BeliefMemory, seed_bot_02_record
from declarative.conflicts import resolve_priority
from declarative.database import BeliefDatabase

UTC_1 = "2026-10-03T09:15:00Z"
UTC_2 = "2026-10-03T09:16:02Z"
UTC_OLD = "2025-01-01T09:00:00Z"


def data(result: dict[str, object]) -> object:
    """Extract successful ToolResult data for concise test assertions."""
    assert result["ok"] is True
    return result["data"]


def test_update_supersedes_without_erasing_history() -> None:
    """Use a strong live sensor against older history and preserve the old record."""
    memory = BeliefMemory()
    first = data(
        memory.add_belief(
            "path_A", "status", "clear", "default_map", 1.0, "historical", UTC_1
        )
    )
    updated = data(
        memory.update_belief(
            "path_A",
            "status",
            "blocked",
            "lidar_front",
            0.98,
            "agent_sensor",
            "live reading",
            UTC_2,
        )
    )
    history = data(memory.get_belief_history("path_A", "status"))
    assert len(history) == 2
    assert updated["supersedes"] == first["belief_id"]
    assert first["status"] == "active"
    assert history[0]["status"] == "superseded"
    assert history[0]["valid_to"] == UTC_2
    assert [item["object"] for item in history] == ["clear", "blocked"]
    memory.close()


def test_update_same_perspective_closes_old_validity() -> None:
    """Supersede a prior claim from the same perspective while preserving its record."""
    memory = BeliefMemory()
    memory.add_belief("box_01", "color", "blue", "archive", 0.8, "historical", UTC_1)
    changed = data(
        memory.update_belief(
            "box_01",
            "color",
            "green",
            "archive",
            0.9,
            "historical",
            "new historical record",
            UTC_2,
        )
    )
    old = data(memory.get_belief_history("box_01", "color"))[0]
    assert changed["supersedes"] == old["belief_id"]
    assert old["status"] == "superseded"
    assert old["valid_to"] == UTC_2
    memory.close()


def test_missing_provenance_caps_confidence() -> None:
    """Cap unprovenanced claims at 0.5 as specified by contract policy."""
    memory = BeliefMemory()
    item = data(memory.add_belief("box_01", "color", "red", None, 0.9, "user", UTC_1))
    assert item["confidence"] == 0.5
    memory.close()


def test_query_filters_perspective_and_conflict_detection() -> None:
    """Keep three viewpoints queryable, including superseded historical evidence."""
    memory = BeliefMemory()
    memory.add_belief("box_01", "color", "red", "user", 0.7, "user", UTC_1)
    memory.add_belief(
        "box_01", "color", "blue", "stored_history", 0.8, "historical", UTC_OLD
    )
    memory.update_belief(
        "box_01",
        "color",
        "brown",
        "camera_front",
        0.92,
        "agent_sensor",
        "camera observation",
        UTC_2,
    )
    assert len(data(memory.query_belief("box_01", "color", "user"))) == 1
    sensor_view = data(memory.query_belief("box_01", "color", "agent_sensor"))
    history_view = data(memory.query_belief("box_01", "color", "historical"))
    assert sensor_view[0]["object"] == "brown"
    assert history_view[0]["object"] == "blue"
    assert history_view[0]["status"] == "superseded"
    conflicts = data(memory.detect_conflict("box_01", "color"))
    assert len(conflicts) == 2
    memory.close()


def test_weak_sensor_is_recorded_as_disputed_not_overwriting_strong_history() -> None:
    """Keep a weak sensor result disputed when it conflicts with strong history."""
    memory = BeliefMemory()
    memory.add_belief(
        "path_A", "status", "clear", "default_map", 0.9, "historical", UTC_1
    )
    result = data(
        memory.update_belief(
            "path_A",
            "status",
            "blocked",
            "lidar_front",
            0.3,
            "agent_sensor",
            "low-confidence reading",
            UTC_2,
        )
    )
    assert result["status"] == "disputed"
    assert result["supersedes"] is None
    history = data(memory.get_belief_history("path_A", "status"))
    assert [item["status"] for item in history] == ["active", "disputed"]
    memory.close()


def test_downgrade_then_sensor_update_keeps_the_full_supersession_chain() -> None:
    """Retain the original claim and downgrade when the current sensor replaces it."""
    memory = BeliefMemory(clock=lambda: UTC_2)
    original = data(
        memory.add_belief(
            "path_A", "status", "clear", "default_map", 1.0, "historical", UTC_1
        )
    )
    reduced = data(memory.downgrade_belief(original["belief_id"], 0.5, "map is stale"))
    sensor = data(
        memory.update_belief(
            "path_A",
            "status",
            "blocked",
            "lidar_front",
            0.98,
            "agent_sensor",
            "new LiDAR reading",
            "2026-10-03T09:17:00Z",
        )
    )
    history = data(memory.get_belief_history("path_A", "status"))
    assert reduced["confidence"] == 0.5
    assert sensor["supersedes"] == reduced["belief_id"]
    assert [belief["status"] for belief in history] == [
        "superseded",
        "superseded",
        "active",
    ]
    assert len(memory.snapshot()["edges"]) == 2
    memory.close()


def test_supersede_and_insert_roll_back_together_on_database_failure() -> None:
    """Keep the original active record when inserting a successor fails."""
    database = BeliefDatabase()
    original = Belief(
        schema_version="1.0",
        belief_id="b_000001",
        subject="path_A",
        predicate="status",
        object="clear",
        source="default_map",
        confidence=1.0,
        timestamp=UTC_1,
        perspective="historical",
        status="active",
        valid_from=UTC_1,
        valid_to=None,
        supersedes=None,
    )
    duplicate_id = original.model_copy(update={"timestamp": UTC_2, "valid_from": UTC_2})
    database.insert(original)
    with pytest.raises(sqlite3.IntegrityError):
        database.append_with_supersession(original, duplicate_id)
    assert database.get("b_000001").status == "active"
    database.close()


def test_contract_round_trip_and_graph_snapshot() -> None:
    """Return JSON-valid beliefs and graph snapshots with a supersession edge."""
    memory = BeliefMemory()
    first = data(
        memory.add_belief("path_A", "status", "clear", "map", 1.0, "historical", UTC_1)
    )
    memory.update_belief(
        "path_A",
        "status",
        "blocked",
        "lidar_front",
        0.98,
        "historical",
        "new map reading",
        UTC_2,
    )
    assert Belief.model_validate(first).belief_id == "b_000001"
    assert len(memory.snapshot()["nodes"]) == 2
    memory.close()


def test_evidence_priority_rules_are_deterministic() -> None:
    """Prioritize a strong live sensor over history and dispute weak evidence."""
    old = Belief.model_validate(
        {
            "schema_version": "1.0",
            "belief_id": "b_000123",
            "subject": "path_A",
            "predicate": "status",
            "object": "clear",
            "source": "default_map",
            "confidence": 1.0,
            "timestamp": UTC_1,
            "perspective": "historical",
            "status": "active",
            "valid_from": UTC_1,
            "valid_to": None,
            "supersedes": None,
        }
    )
    strong = SensorReading(
        schema_version="1.0",
        sensor="lidar_front",
        value=12,
        unit="cm",
        status="blocked",
        timestamp=UTC_2,
        confidence=0.98,
    )
    weak = strong.model_copy(update={"confidence": 0.3})
    assert resolve_priority(old, strong).action == "replace"
    assert resolve_priority(old, weak).action == "dispute"
    assert (
        resolve_priority(old, strong, another_live_sensor_disagrees=True).action
        == "dispute"
    )


def test_bot_02_provenance_is_queryable_as_third_party() -> None:
    """Seed a caller-supplied bot_02 claim without hard-coding a Scenario B fact."""
    memory = BeliefMemory()
    seeded = data(
        seed_bot_02_record(
            memory,
            "fixture_object",
            "fixture_claim",
            "sample",
            0.8,
            UTC_1,
        )
    )
    assert seeded["source"] == "bot_02"
    assert seeded["perspective"] == "third_party"
    found = data(memory.query_belief("fixture_object", "fixture_claim", "third_party"))
    assert found[0]["belief_id"] == seeded["belief_id"]
    memory.close()


def test_memory_emits_committed_change_events() -> None:
    """Send successful memory mutations to the injected event logger callback."""
    events: list[tuple[str, dict[str, object]]] = []
    memory = BeliefMemory(
        event_callback=lambda kind, details: events.append((kind, details))
    )
    memory.add_belief(
        "path_A", "status", "clear", "default_map", 1.0, "historical", UTC_1
    )
    memory.update_belief(
        "path_A",
        "status",
        "blocked",
        "lidar_front",
        0.98,
        "agent_sensor",
        "live sensor",
        UTC_2,
    )
    assert [kind for kind, _ in events] == ["belief_created", "belief_update"]
    assert events[1][1]["operation"] == "replace"
    memory.close()
