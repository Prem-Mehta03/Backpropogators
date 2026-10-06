"""Scenario configuration: immutable dataclasses plus a validating loader.

Plain Python only (no contracts, no other layer). A scenario file is JSON; see
``sensorimotor/scenarios/scenario_a.json`` for the full shape.

Conventions
-----------
* Distances are cm. The world is a 2-D plane; the +x axis is heading 0 deg.
* Positive turns are counter-clockwise. Headings are in [0, 360).
* Timestamps are ISO 8601 UTC with a trailing Z.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCENARIO_DIR = Path(__file__).parent / "scenarios"
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CHANGE_TYPES = ("add_obstacle", "remove_obstacle", "set_lighting", "set_object_color")


class ScenarioConfigError(ValueError):
    """Raised at setup time when a scenario file or dict is invalid."""


@dataclass(frozen=True)
class RobotConfig:
    x: float
    y: float
    heading_deg: float


@dataclass(frozen=True)
class ObstacleConfig:
    obstacle_id: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass(frozen=True)
class ObjectConfig:
    object_id: str
    x: float
    y: float
    true_color: str


@dataclass(frozen=True)
class LightingConfig:
    """``color_shift`` maps a true colour to the colour a camera reports."""

    name: str = "white"
    color_shift: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LidarConfig:
    name: str
    direction: str
    max_range_cm: float
    blocked_threshold_cm: float
    confidence: float
    noise_std_cm: float = 0.0
    available: bool = True


@dataclass(frozen=True)
class CameraConfig:
    name: str = "camera_front"
    fov_deg: float = 60.0
    max_range_cm: float = 300.0
    confidence: float = 0.9
    available: bool = True


@dataclass(frozen=True)
class PositionConfig:
    name: str = "position"
    confidence: float = 1.0
    available: bool = True


@dataclass(frozen=True)
class EventConfig:
    """A world change applied when the step counter reaches ``at_step``."""

    at_step: int
    change: Mapping[str, Any]


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    description: str
    seed: int
    start_time: str
    tick_seconds: float
    collision_margin_cm: float
    max_move_cm: float
    robot: RobotConfig
    lighting: LightingConfig
    obstacles: tuple[ObstacleConfig, ...]
    objects: tuple[ObjectConfig, ...]
    lidars: tuple[LidarConfig, ...]
    camera: CameraConfig
    position: PositionConfig
    events: tuple[EventConfig, ...]


# ---------------------------------------------------------------- helpers
def _num(d: Mapping[str, Any], key: str, default: float | None = None) -> float:
    val = d.get(key, default)
    if val is None:
        raise ScenarioConfigError(f"Missing required number '{key}'")
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ScenarioConfigError(f"'{key}' must be a number, got {val!r}")
    if not math.isfinite(val):
        raise ScenarioConfigError(f"'{key}' must be finite")
    return float(val)


def _str(d: Mapping[str, Any], key: str, default: str | None = None) -> str:
    val = d.get(key, default)
    if not isinstance(val, str) or not val:
        raise ScenarioConfigError(f"'{key}' must be a non-empty string, got {val!r}")
    return val


def _conf(d: Mapping[str, Any], default: float) -> float:
    c = _num(d, "confidence", default)
    if not 0.0 <= c <= 1.0:
        raise ScenarioConfigError(f"'confidence' must be in [0, 1], got {c}")
    return c


def _bool(d: Mapping[str, Any], key: str, default: bool) -> bool:
    val = d.get(key, default)
    if not isinstance(val, bool):
        raise ScenarioConfigError(f"'{key}' must be true or false")
    return val


def _obstacle(d: Mapping[str, Any]) -> ObstacleConfig:
    ob = ObstacleConfig(
        _str(d, "obstacle_id"),
        _num(d, "x_min"),
        _num(d, "y_min"),
        _num(d, "x_max"),
        _num(d, "y_max"),
    )
    if ob.x_min >= ob.x_max or ob.y_min >= ob.y_max:
        raise ScenarioConfigError(f"Obstacle {ob.obstacle_id}: min must be < max")
    return ob


def parse_timestamp(ts: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp ending in Z."""
    try:
        return datetime.strptime(ts, TS_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ScenarioConfigError(f"Bad timestamp {ts!r}; expected ...Z") from exc


def _lighting(d: Mapping[str, Any]) -> LightingConfig:
    shift = d.get("color_shift", {})
    if not isinstance(shift, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in shift.items()
    ):
        raise ScenarioConfigError("lighting.color_shift must map string to string")
    return LightingConfig(_str(d, "name", "white"), dict(shift))


def _event(d: Mapping[str, Any]) -> EventConfig:
    step = int(_num(d, "at_step"))
    change = d.get("change")
    if not isinstance(change, dict) or change.get("type") not in CHANGE_TYPES:
        raise ScenarioConfigError(f"event.change.type must be one of {CHANGE_TYPES}")
    return EventConfig(step, dict(change))


# ----------------------------------------------------------------- loader
def parse_scenario(raw: Mapping[str, Any]) -> ScenarioConfig:
    """Validate a scenario dict and return an immutable ScenarioConfig."""
    if not isinstance(raw, Mapping):
        raise ScenarioConfigError("Scenario must be a JSON object")
    robot_raw = raw.get("robot")
    if not isinstance(robot_raw, dict):
        raise ScenarioConfigError("Scenario needs a 'robot' object")
    sensors = raw.get("sensors", {})

    lidars: list[LidarConfig] = []
    for item in sensors.get("lidar", []):
        lidars.append(
            LidarConfig(
                name=_str(item, "name"),
                direction=_str(item, "direction", "front"),
                max_range_cm=_num(item, "max_range_cm", 400),
                blocked_threshold_cm=_num(item, "blocked_threshold_cm", 30),
                confidence=_conf(item, 0.98),
                noise_std_cm=_num(item, "noise_std_cm", 0),
                available=_bool(item, "available", True),
            )
        )
    names = [s.name for s in lidars]
    if len(set(names)) != len(names):
        raise ScenarioConfigError("Duplicate lidar names")

    cam_raw = sensors.get("camera", {})
    pos_raw = sensors.get("position", {})
    start = _str(raw, "start_time", "2026-10-03T09:00:00Z")
    parse_timestamp(start)

    return ScenarioConfig(
        name=_str(raw, "name"),
        description=str(raw.get("description", "")),
        seed=int(_num(raw, "seed", 0)),
        start_time=start,
        tick_seconds=_num(raw, "tick_seconds", 1),
        collision_margin_cm=_num(raw, "collision_margin_cm", 1),
        max_move_cm=_num(raw, "max_move_cm", 500),
        robot=RobotConfig(
            _num(robot_raw, "x", 0),
            _num(robot_raw, "y", 0),
            _num(robot_raw, "heading_deg", 0) % 360.0,
        ),
        lighting=_lighting(raw.get("lighting", {})),
        obstacles=tuple(_obstacle(o) for o in raw.get("obstacles", [])),
        objects=tuple(
            ObjectConfig(_str(o, "object_id"), _num(o, "x"), _num(o, "y"), _str(o, "true_color"))
            for o in raw.get("objects", [])
        ),
        lidars=tuple(lidars),
        camera=CameraConfig(
            name=_str(cam_raw, "name", "camera_front"),
            fov_deg=_num(cam_raw, "fov_deg", 60),
            max_range_cm=_num(cam_raw, "max_range_cm", 300),
            confidence=_conf(cam_raw, 0.9),
            available=_bool(cam_raw, "available", True),
        ),
        position=PositionConfig(
            name=_str(pos_raw, "name", "position"),
            confidence=_conf(pos_raw, 1.0),
            available=_bool(pos_raw, "available", True),
        ),
        events=tuple(_event(e) for e in raw.get("events", [])),
    )


def load_scenario(source: str | Path | Mapping[str, Any]) -> ScenarioConfig:
    """Load a scenario by built-in name ("scenario_a"), file path, or dict."""
    if isinstance(source, Mapping):
        return parse_scenario(source)
    path = Path(source)
    if not path.suffix:  # bare name -> built-in scenario folder
        path = SCENARIO_DIR / f"{source}.json"
    if not path.is_file():
        raise ScenarioConfigError(f"Scenario file not found: {path}")
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioConfigError(f"{path.name} is not valid JSON: {exc}") from exc
    return parse_scenario(raw)


def list_scenarios() -> list[str]:
    """Names of the built-in scenario files."""
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))
