"""STUB of Asvin's sensor and action API. Returns fixed, valid contract JSON.

Scenario A fixture: lidar_front reads 12 cm, blocked. Scenario B fixture: the camera sees a
brown box_01. Position and moves are fixed fixtures too (the stub has no world state).
Replace with the real sensorimotor functions; signatures and envelopes stay the same.
Placeholder owned by Asvin's real code: do not commit.
"""

from __future__ import annotations

from typing import Any

from contracts.models import SensorReading, ToolResult

FIXED_TS = "2026-10-03T09:16:02Z"


def _ok(tool: str, reading: SensorReading) -> dict[str, Any]:
    return ToolResult(
        schema_version="1.0",
        tool=tool,
        ok=True,
        data=reading.model_dump(),
        error=None,
        timestamp=FIXED_TS,
    ).model_dump()


def _fail(tool: str, code: str, message: str) -> dict[str, Any]:
    return ToolResult.model_validate(
        {
            "schema_version": "1.0",
            "tool": tool,
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message, "retryable": False},
            "timestamp": FIXED_TS,
        }
    ).model_dump()


def _position(x_cm: float, heading_deg: float) -> SensorReading:
    return SensorReading(
        schema_version="1.0",
        sensor="position",
        value={"x_cm": x_cm, "y_cm": 0, "heading_deg": heading_deg},
        unit=None,
        status="clear",
        timestamp=FIXED_TS,
        confidence=1.0,
    )


def read_lidar(direction: str = "front") -> dict[str, Any]:
    """Read the LiDAR. Input: direction (default "front").

    Returns a ToolResult envelope dict. Error codes: INVALID_ARGUMENT for a direction
    other than "front".
    """
    if direction != "front":
        return _fail(
            "read_lidar", "INVALID_ARGUMENT", f"Unsupported direction: {direction}"
        )
    reading = SensorReading(
        schema_version="1.0",
        sensor="lidar_front",
        value=12,
        unit="cm",
        status="blocked",
        timestamp=FIXED_TS,
        confidence=0.98,
    )
    return _ok("read_lidar", reading)


def read_camera(target: str | None = None) -> dict[str, Any]:
    """Read the camera. Input: optional object id. Error codes: NOT_FOUND for an unknown id."""
    if target not in (None, "box_01"):
        return _fail("read_camera", "NOT_FOUND", f"No object {target} in view")
    reading = SensorReading(
        schema_version="1.0",
        sensor="camera_front",
        value={"object_id": "box_01", "color": "brown"},
        unit=None,
        status="clear",
        timestamp=FIXED_TS,
        confidence=0.9,
    )
    return _ok("read_camera", reading)


def get_position() -> dict[str, Any]:
    """Return the robot position as a fixed fixture."""
    return _ok("get_position", _position(0, 0))


def move_forward(distance_cm: float) -> dict[str, Any]:
    """Move forward (fixture: the new x equals the distance). Returns the position."""
    return _ok("move_forward", _position(distance_cm, 0))


def move_backward(distance_cm: float) -> dict[str, Any]:
    """Move backward (fixture: the new x is minus the distance). Returns the position."""
    return _ok("move_backward", _position(-distance_cm, 0))


def turn(degrees: float) -> dict[str, Any]:
    """Turn (fixture: the new heading equals the angle). Returns the position."""
    return _ok("turn", _position(0, degrees))
