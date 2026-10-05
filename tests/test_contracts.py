"""Contract validation tests maintained by the contract owner."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.models import Belief, SensorReading, ToolResult
from contracts.validators import error_result, success_result

UTC = "2026-10-03T09:15:00Z"


def belief_payload(**overrides: object) -> dict[str, object]:
    """Return a valid contract belief mapping with optional field overrides."""
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "belief_id": "b_000123",
        "subject": "path_A",
        "predicate": "status",
        "object": "clear",
        "source": "default_map",
        "confidence": 1.0,
        "timestamp": UTC,
        "perspective": "historical",
        "status": "active",
        "valid_from": UTC,
        "valid_to": None,
        "supersedes": None,
    }
    payload.update(overrides)
    return payload


def test_belief_accepts_contract_v1_payload() -> None:
    """Accept a fully populated version 1.0 belief."""
    assert Belief.model_validate(belief_payload()).belief_id == "b_000123"


@pytest.mark.parametrize(
    "override",
    [
        {"extra": "forbidden"},
        {"belief_id": "belief-123"},
        {"confidence": 1.1},
        {"timestamp": "2026-10-03T09:15:00+00:00"},
        {"perspective": "unknown"},
        {"confidence": "0.8"},
    ],
)
def test_belief_rejects_contract_violations(override: dict[str, object]) -> None:
    """Reject extra fields, invalid enums, timestamps, IDs, and coercions."""
    with pytest.raises(ValidationError):
        Belief.model_validate(belief_payload(**override))


def test_sensor_reading_accepts_object_value() -> None:
    """Allow structured camera readings while preserving the shared envelope fields."""
    reading = SensorReading(
        schema_version="1.0",
        sensor="camera_front",
        value={"object_id": "box_01", "color": "brown"},
        unit=None,
        status="clear",
        timestamp=UTC,
        confidence=0.92,
    )
    assert reading.value["color"] == "brown"


def test_tool_result_success_and_error_envelopes_validate() -> None:
    """Validate both required ToolResult envelope shapes."""
    ok = success_result("query_belief", [])
    error = error_result("query_belief", "NOT_FOUND", "No matching belief")
    assert ToolResult.model_validate(ok).ok is True
    assert ToolResult.model_validate(error).error.code == "NOT_FOUND"


def test_tool_result_rejects_inconsistent_failure_shape() -> None:
    """Reject a failed envelope without its required error payload."""
    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {
                "schema_version": "1.0",
                "tool": "query_belief",
                "ok": False,
                "data": [],
                "error": None,
                "timestamp": UTC,
            }
        )


def test_schema_version_is_required_on_every_boundary_model() -> None:
    """Reject boundary payloads that omit the required schema version."""
    payload = belief_payload()
    payload.pop("schema_version")
    with pytest.raises(ValidationError):
        Belief.model_validate(payload)

    reading = {
        "sensor": "lidar_front",
        "value": 12,
        "unit": "cm",
        "status": "blocked",
        "timestamp": UTC,
        "confidence": 0.98,
    }
    with pytest.raises(ValidationError):
        SensorReading.model_validate(reading)

    result = {
        "tool": "query_belief",
        "ok": True,
        "data": [],
        "error": None,
        "timestamp": UTC,
    }
    with pytest.raises(ValidationError):
        ToolResult.model_validate(result)


def test_contracts_reject_non_json_and_non_finite_values() -> None:
    """Reject values that Python can hold but JSON cannot represent safely."""
    with pytest.raises(ValidationError):
        Belief.model_validate(belief_payload(object=float("nan")))

    with pytest.raises(ValidationError):
        SensorReading.model_validate(
            {
                "schema_version": "1.0",
                "sensor": "camera_front",
                "value": {"colors": {1: "brown"}},
                "unit": None,
                "status": "clear",
                "timestamp": UTC,
                "confidence": 0.9,
            }
        )

    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {
                "schema_version": "1.0",
                "tool": "query_belief",
                "ok": True,
                "data": [float("inf")],
                "error": None,
                "timestamp": UTC,
            }
        )
