"""Stub of the sensorimotor API, published early so other layers can code against it.

Every function builds a fresh, fixed world (Scenario A, or Scenario B for the
camera) and returns a real ToolResult envelope dict, so results are repeatable
fixtures and there is no shared state. For stateful runs, where actions change
later readings, use ``create_sensorimotor()`` and ``tool_registry()`` instead.
"""

from __future__ import annotations

from typing import Any

from . import create_sensorimotor


def _a() -> Any:
    return create_sensorimotor("scenario_a", seed=42)


def read_lidar(direction: str = "front") -> dict[str, Any]:
    """Scenario A fixture: lidar_front reads 12 cm, blocked."""
    return _a().sensors.read_lidar(direction)


def read_camera(target: str | None = None) -> dict[str, Any]:
    """Scenario B fixture: box_01 reads brown under yellow light."""
    return create_sensorimotor("scenario_b", seed=42).sensors.read_camera(target)


def get_position() -> dict[str, Any]:
    """Scenario A starting pose."""
    return _a().sensors.get_position()


def move_forward(distance_cm: float) -> dict[str, Any]:
    return _a().actions.move_forward(distance_cm)


def move_backward(distance_cm: float) -> dict[str, Any]:
    return _a().actions.move_backward(distance_cm)


def turn(degrees: float) -> dict[str, Any]:
    return _a().actions.turn(degrees)
