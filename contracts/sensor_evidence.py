"""Interpret the documented subject, predicate and value of a sensor observation."""

from collections.abc import Mapping
import math
from typing import Any

from contracts.models import SensorReading

FRONT_RANGE_SENSORS = frozenset({"lidar_front", "ultrasonic_front"})
CAMERA_SENSOR = "camera_front"


def reading_claim(
    reading: SensorReading | Mapping[str, Any],
) -> tuple[str, str, str] | None:
    """Return the verifiable claim carried by a usable front range or camera reading."""
    data = reading.model_dump() if isinstance(reading, SensorReading) else reading
    sensor, status, value = data.get("sensor"), data.get("status"), data.get("value")
    if status not in {"clear", "blocked"}:
        return None
    if sensor in FRONT_RANGE_SENSORS:
        if (
            data.get("unit") != "cm"
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            or (isinstance(value, float) and not math.isfinite(value))
        ):
            return None
        return "path_A", "status", status
    if sensor == CAMERA_SENSOR and isinstance(value, Mapping):
        subject, color = value.get("object_id"), value.get("color")
        if (
            isinstance(subject, str) and subject.strip()
            and isinstance(color, str) and color.strip()
        ):
            return subject, "color", color
    return None
