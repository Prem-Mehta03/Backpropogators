"""Recheck the simulated direction of travel before dispatching a translation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from contracts.models import SensorReading
from contracts.policy import RECHECK_MARGIN_CM
from procedural.tools import ToolFn, call_tool

# The front ultrasonic sensor cannot see beyond its range (200 cm, handoff D2): on a clear path it
# reports that range. A reading at its range therefore means "nothing within range", and is
# compared with the range, not with a longer move distance (live: with the ultrasonic enabled,
# every move of 171 cm or more was cancelled although the path was clear). The LiDAR, which
# reaches 400 cm, still has to clear the whole distance plus the margin.
ULTRASONIC_RANGE_CM = 200
MOVE_DIRECTIONS = {"move_forward": "front", "move_backward": "back"}
RECHECK_PHRASE = "recheck before action"


@dataclass(frozen=True)
class RecheckResult:
    """Details for the move's log entry, with a cancel reason when movement is refused."""

    details: dict[str, Any]
    cancel: str | None = None


def _motion_distance(reading: SensorReading, tool: str, direction: str) -> float | None:
    if tool == "read_ultrasonic":
        expected = {"ultrasonic_front"}
    else:
        expected = (
            {"lidar_front"} if direction == "front" else {"lidar_back", "lidar_rear"}
        )
    if (
        reading.sensor not in expected
        or reading.unit != "cm"
        or reading.status not in {"clear", "blocked"}
        or isinstance(reading.value, bool)
        or not isinstance(reading.value, (int, float))
        or reading.value < 0
    ):
        return None
    return reading.value


def recheck_before_action(
    tool: str,
    arguments: dict[str, Any],
    registry: dict[str, ToolFn],
    on_read: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
) -> RecheckResult | None:
    """Read each range sensor facing the move and fail closed on unsafe or missing data.

    Inputs: model tool and arguments, registry, optional observer after each read.
    Returns no recheck for non-moves or malformed distances. Otherwise returns details and
    an optional cancel message, which the caller wraps in a CONFLICT ToolResult.

    An enabled front ultrasonic sensor can veto either direction conservatively. It
    never substitutes for a rear LiDAR when moving backward.
    """
    direction = MOVE_DIRECTIONS.get(tool)
    distance = arguments.get("distance_cm")
    if (
        direction is None
        or isinstance(distance, bool)
        or not isinstance(distance, (int, float))
    ):
        return None
    if distance <= 0 or (isinstance(distance, float) and not math.isfinite(distance)):
        return None
    need = distance + RECHECK_MARGIN_CM
    checks: list[tuple[str, dict[str, Any]]] = [
        ("read_lidar", {"direction": direction})
    ]
    if "read_ultrasonic" in registry:
        checks.append(("read_ultrasonic", {}))
    details: dict[str, Any] = {
        "direction": direction,
        "requested_cm": distance,
        "margin_cm": RECHECK_MARGIN_CM,
        "required_cm": need,
        "reads": [],
    }
    failures: list[str] = []
    for name, args in checks:
        envelope = call_tool(name, args, registry)
        details["reads"].append(
            {"tool": name, "args": args, "result": envelope, "auto": True}
        )
        if on_read is not None:
            on_read(name, args, envelope)
        is_lidar = name == "read_lidar"
        details["lidar_result" if is_lidar else "ultrasonic_result"] = envelope
        label = f"{direction} LiDAR" if is_lidar else "front ultrasonic sensor"
        if not envelope["ok"]:
            failures.append(
                f"The {label} could not be read ({envelope['error']['message']})."
            )
            continue
        try:
            reading = SensorReading.model_validate(envelope["data"])
        except ValueError:
            failures.append(f"The {label} returned an unusable reading.")
            continue
        value = _motion_distance(reading, name, direction)
        if is_lidar:
            details["reading_cm"] = value
        if value is None:
            failures.append(
                f"The {label} returned an unusable reading (status {reading.status})."
            )
        elif reading.status == "blocked" or value < (
            need if is_lidar else min(need, ULTRASONIC_RANGE_CM)
        ):
            required = need if is_lidar else min(need, ULTRASONIC_RANGE_CM)
            failures.append(
                f"The {label} now reads {value} cm (status {reading.status}). "
                f"Clearance must be at least {required} cm including the {RECHECK_MARGIN_CM} cm margin."
            )
    details["passed"] = not failures
    if not failures:
        return RecheckResult(details)
    details["reason"] = " ".join(failures)
    return RecheckResult(
        details,
        f"Move cancelled: {RECHECK_PHRASE}. {details['reason']} "
        "The robot did not move. Report the readings and that the move was cancelled.",
    )
