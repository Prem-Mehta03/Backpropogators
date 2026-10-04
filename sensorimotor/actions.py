"""Actions: move_forward, move_backward, turn.

Each tool validates its argument, changes the environment through
``MockEnvironment.step`` and returns the new pose as a position SensorReading
inside a ToolResult envelope (Guidelines 4.5). Later sensor readings therefore
reflect the action.

Draft choices (not in the docs; confirm if they matter to someone else):
  * a move that is cut short by an obstacle still returns ok=true, with the
    position reading's status set to "blocked";
  * positive ``degrees`` turn counter-clockwise; |degrees| <= 360;
  * ``distance_cm`` must be > 0 and <= scenario ``max_move_cm``.
"""

from __future__ import annotations

import math
from typing import Any

from . import _boundary as bd
from .mock_env import MockEnvironment
from .sensors import measure_position, to_reading


def _check_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise bd.ToolFailure("INVALID_ARGUMENT", f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise bd.ToolFailure("INVALID_ARGUMENT", f"{name} must be finite")
    return float(value)


class Actions:
    """Tool-facing action API. Construct with an environment; no global state."""

    def __init__(self, env: MockEnvironment) -> None:
        self._env = env

    def _act(self, action: str, amount: float):
        cfg = self._env.scenario.position
        if not cfg.available:
            raise bd.ToolFailure(
                "SENSOR_UNAVAILABLE", "Position sensor is unavailable; action not executed", True
            )
        outcome = self._env.step(action, amount)
        status = "blocked" if outcome.blocked else "clear"
        return to_reading(measure_position(self._env, cfg.name, cfg.confidence, status))

    def _move(self, tool: str, action: str, distance_cm: Any):
        def body():
            d = _check_number(distance_cm, "distance_cm")
            limit = self._env.scenario.max_move_cm
            if d <= 0 or d > limit:
                raise bd.ToolFailure(
                    "INVALID_ARGUMENT", f"distance_cm must be > 0 and <= {limit}, got {d}"
                )
            return self._act(action, d)

        return bd.run_tool(tool, self._env.now_iso, body)

    def move_forward(self, distance_cm: float):
        """Move along the heading. Args: distance_cm (> 0).

        Returns a ToolResult envelope dict; data is the position SensorReading. Errors:
        INVALID_ARGUMENT, SENSOR_UNAVAILABLE.
        """
        return self._move("move_forward", "move_forward", distance_cm)

    def move_backward(self, distance_cm: float):
        """Move opposite the heading. Args: distance_cm (> 0). Same returns/errors."""
        return self._move("move_backward", "move_backward", distance_cm)

    def turn(self, degrees: float):
        """Rotate in place. Args: degrees (+ = counter-clockwise, |degrees| <= 360).

        Returns a ToolResult envelope dict; data is the position SensorReading. Errors:
        INVALID_ARGUMENT, SENSOR_UNAVAILABLE.
        """

        def body():
            deg = _check_number(degrees, "degrees")
            if abs(deg) > 360:
                raise bd.ToolFailure("INVALID_ARGUMENT", f"|degrees| must be <= 360, got {deg}")
            return self._act("turn", deg)

        return bd.run_tool("turn", self._env.now_iso, body)
