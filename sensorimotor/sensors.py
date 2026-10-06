"""Sensors: LiDAR, camera (with lighting model) and position.

Two levels:
  * ``measure_*`` functions are pure: environment in, ``RawReading`` out, no
    contract models, fully testable on their own.
  * ``Sensors`` exposes the tool functions from Guidelines 4.5
    (``read_lidar``, ``read_camera``, ``get_position``). Each returns a
    ToolResult envelope built in ``_boundary`` and never raises.

Decided default: the contract does not say which ``status`` a camera reading
carries, so CAMERA_OBSERVED_STATUS / CAMERA_NOT_SEEN_STATUS below are my
choice (see the Interface Guide, section 7).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from . import _boundary as bd
from .config import CameraConfig, LidarConfig, LightingConfig
from .mock_env import MockEnvironment

CAMERA_OBSERVED_STATUS = "clear"
CAMERA_NOT_SEEN_STATUS = "unknown"
DIRECTION_OFFSETS: dict[str, float] = {
    "front": 0.0,
    "left": 90.0,
    "back": 180.0,
    "right": 270.0,
}


@dataclass(frozen=True)
class RawReading:
    """Plain-Python mirror of the SensorReading fields (no contract import)."""

    sensor: str
    value: int | float | str | dict[str, Any]
    unit: str | None
    status: str
    timestamp: str
    confidence: float


def _clean(x: float) -> int | float:
    """Round to 2 dp; whole numbers become int (12.0 -> 12, matching the contract example)."""
    r = round(float(x), 2)
    return int(r) if r == int(r) else r


def apparent_color(true_color: str, lighting: LightingConfig) -> str:
    """Lighting model: the colour the camera reports for an object's true colour."""
    return lighting.color_shift.get(true_color, true_color)


# ------------------------------------------------------------ pure measures
def measure_lidar(env: MockEnvironment, cfg: LidarConfig) -> RawReading:
    """Distance to the nearest obstacle along the sensor direction."""
    offset = DIRECTION_OFFSETS[cfg.direction]
    dist = env.ray_distance(offset, cfg.max_range_cm)
    if dist is None:
        value = cfg.max_range_cm  # nothing in range
    else:
        value = min(max(dist + env.noise(cfg.name, cfg.noise_std_cm), 0.0), cfg.max_range_cm)
    status = "blocked" if value <= cfg.blocked_threshold_cm else "clear"
    return RawReading(cfg.name, _clean(value), "cm", status, env.now_iso(), cfg.confidence)


def _bearing_and_range(env: MockEnvironment, x: float, y: float) -> tuple:
    pose = env.pose
    dx, dy = x - pose["x"], y - pose["y"]
    bearing = (math.degrees(math.atan2(dy, dx)) - pose["heading_deg"] + 180.0) % 360.0 - 180.0
    return bearing, math.hypot(dx, dy)


def measure_camera(
    env: MockEnvironment, cfg: CameraConfig, target: str | None = None
) -> RawReading:
    """What the front camera reports.

    ``target=None``: nearest object inside the field of view and range.
    ``target=<object_id>``: that object only. Caller checks the id exists.
    Nothing visible gives status "unknown" with null object_id/color.
    """
    visible = []
    for obj in env.objects.values():
        if target is not None and obj.object_id != target:
            continue
        bearing, dist = _bearing_and_range(env, obj.x, obj.y)
        if dist <= cfg.max_range_cm and abs(bearing) <= cfg.fov_deg / 2.0:
            visible.append((dist, obj))
    ts = env.now_iso()
    if not visible:
        value = {"object_id": target, "color": None}
        return RawReading(cfg.name, value, None, CAMERA_NOT_SEEN_STATUS, ts, cfg.confidence)
    _, obj = min(visible, key=lambda t: (t[0], t[1].object_id))
    value = {"object_id": obj.object_id, "color": apparent_color(obj.true_color, env.lighting)}
    return RawReading(cfg.name, value, None, CAMERA_OBSERVED_STATUS, ts, cfg.confidence)


def measure_position(
    env: MockEnvironment, name: str, confidence: float, status: str = "clear"
) -> RawReading:
    """Robot pose as a reading: value {x, y, heading_deg}; x and y in cm."""
    pose = env.pose
    value = {k: _clean(v) for k, v in pose.items()}
    return RawReading(name, value, None, status, env.now_iso(), confidence)


def to_reading(raw: RawReading):
    """RawReading -> validated SensorReading (the contract boundary)."""
    return bd.build_reading(**asdict(raw))


# ------------------------------------------------------------- tool surface
class Sensors:
    """Tool-facing sensor API. Construct with an environment; no global state."""

    def __init__(self, env: MockEnvironment) -> None:
        self._env = env

    def read_lidar(self, direction: str = "front"):
        """Read a LiDAR. Args: direction in front/back/left/right (default front).

        Returns a ToolResult envelope dict; data is a SensorReading. Errors: INVALID_ARGUMENT (bad
        direction), SENSOR_UNAVAILABLE (not configured or switched off).
        """

        def body():
            if direction not in DIRECTION_OFFSETS:
                raise bd.ToolFailure(
                    "INVALID_ARGUMENT",
                    f"direction must be one of {sorted(DIRECTION_OFFSETS)}, got {direction!r}",
                )
            cfg = next((c for c in self._env.scenario.lidars if c.direction == direction), None)
            if cfg is None or not cfg.available:
                raise bd.ToolFailure(
                    "SENSOR_UNAVAILABLE", f"No working LiDAR for direction '{direction}'", True
                )
            return to_reading(measure_lidar(self._env, cfg))

        return bd.run_tool("read_lidar", self._env.now_iso, body)

    def read_camera(self, target: str | None = None):
        """Read the front camera. Args: target (optional object_id).

        Returns a ToolResult envelope dict; data is a SensorReading. Errors:
        INVALID_ARGUMENT (target not a string), NOT_FOUND (no such object in
        the world), SENSOR_UNAVAILABLE.
        """

        def body():
            cfg = self._env.scenario.camera
            if not cfg.available:
                raise bd.ToolFailure("SENSOR_UNAVAILABLE", "Camera is unavailable", True)
            if target is not None and not isinstance(target, str):
                raise bd.ToolFailure("INVALID_ARGUMENT", "target must be a string object_id")
            if target is not None and target not in self._env.objects:
                raise bd.ToolFailure("NOT_FOUND", f"No object '{target}' in the world")
            return to_reading(measure_camera(self._env, cfg, target))

        return bd.run_tool("read_camera", self._env.now_iso, body)

    def get_position(self):
        """Read the robot pose. No arguments.

        Returns a ToolResult envelope dict; data is a SensorReading. Errors: SENSOR_UNAVAILABLE.
        """

        def body():
            cfg = self._env.scenario.position
            if not cfg.available:
                raise bd.ToolFailure("SENSOR_UNAVAILABLE", "Position sensor is unavailable", True)
            return to_reading(measure_position(self._env, cfg.name, cfg.confidence))

        return bd.run_tool("get_position", self._env.now_iso, body)
