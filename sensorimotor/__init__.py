"""Sensorimotor layer (Role 2, Asvin): simulated world, sensors, actions.

Imports only ``contracts`` (through ``_boundary``). Never imports another layer.

Usage
-----
    from sensorimotor import create_sensorimotor
    sm = create_sensorimotor("scenario_a", seed=42)
    sm.sensors.read_lidar()      # ToolResult envelope (dict)
    sm.actions.move_forward(5)   # ToolResult envelope (dict)
    sm.tool_registry()           # {"read_lidar": fn, ...} for the agent
    sm.env.reset()               # back to the exact starting state
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .actions import Actions
from .config import ScenarioConfigError, list_scenarios, load_scenario
from .mock_env import MockEnvironment
from .sensors import Sensors

__all__ = [
    "Actions",
    "MockEnvironment",
    "ScenarioConfigError",
    "Sensorimotor",
    "Sensors",
    "create_sensorimotor",
    "list_scenarios",
    "load_scenario",
]


@dataclass
class Sensorimotor:
    """One environment with its sensor and action APIs bound to it."""

    env: MockEnvironment
    sensors: Sensors
    actions: Actions

    def tool_registry(self) -> dict[str, Callable[..., dict[str, Any]]]:
        """Tool name -> bound function, for the procedural layer's injected registry.

        Names and argument names match Guidelines 4.5. Every function returns a
        validated ToolResult envelope dict and never raises.
        """
        return {
            "read_lidar": self.sensors.read_lidar,
            "read_camera": self.sensors.read_camera,
            "get_position": self.sensors.get_position,
            "move_forward": self.actions.move_forward,
            "move_backward": self.actions.move_backward,
            "turn": self.actions.turn,
        }


def create_sensorimotor(
    scenario: str | Path | Mapping[str, Any] = "scenario_a",
    seed: int | None = None,
) -> Sensorimotor:
    """Factory: build a fresh, independent environment (no global state)."""
    env = MockEnvironment(load_scenario(scenario), seed)
    return Sensorimotor(env, Sensors(env), Actions(env))
