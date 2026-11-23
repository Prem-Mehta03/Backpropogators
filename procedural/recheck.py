"""Recheck before action (decision D11): the code, not the model, re-reads the LiDAR before a move.

The world can change between the moment the agent decided the route was clear and the moment it
moves (test 10: a cart appears). So before every move_forward or move_backward, this module
reads the LiDAR facing the direction of travel. If the reading is lower than the requested
distance plus RECHECK_MARGIN_CM, or the reading cannot be trusted, the move is cancelled with a
CONFLICT error and never reaches the sensorimotor layer. The model cannot skip or argue with
this check, because it is not a prompt rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from procedural.tools import ToolFn, call_tool

try:
    from contracts.policy import RECHECK_MARGIN_CM
except ImportError:  # pragma: no cover - until contract v1.1 is merged
    RECHECK_MARGIN_CM = 30

# moves that are rechecked, and the LiDAR direction that faces the direction of travel
MOVE_DIRECTIONS = {"move_forward": "front", "move_backward": "back"}
RECHECK_PHRASE = "recheck before action"


@dataclass(frozen=True)
class RecheckResult:
    """Outcome of one recheck: what was compared, and a cancel message when the move is off.

    The automatic LiDAR read is not a separate tool-log entry (the log stays one entry per model
    request); it is recorded in `details`, which the agent stores on the move's own log entry.
    """

    details: dict[
        str, Any
    ]  # what was read and compared; stored on the move's log entry
    cancel: str | None = None  # message for the model when the move is cancelled


def _cancel_message(
    direction: str, reading: dict[str, Any], need: float, d: float
) -> str:
    return (
        f"Move cancelled: {RECHECK_PHRASE}. The {direction} LiDAR now reads "
        f"{reading['value']} cm (status {reading['status']}), which is less than the {d:g} cm "
        f"you asked for plus the {RECHECK_MARGIN_CM:g} cm safety margin ({need:g} cm). The "
        "robot did not move. Report this reading and that the move was cancelled; do not claim "
        "the robot moved. You may ask the person for a shorter distance."
    )


def recheck_before_action(
    tool: str, arguments: dict[str, Any], registry: dict[str, ToolFn]
) -> RecheckResult | None:
    """Read the LiDAR before a move and decide whether the move may run.

    Inputs: the tool the model asked for, its arguments and the tool registry. Output: None for
    any tool that is not a move (or a move with a malformed distance, which the normal argument
    check reports); otherwise a RecheckResult. `cancel` is set when the move must not run.
    """
    direction = MOVE_DIRECTIONS.get(tool)
    distance = arguments.get("distance_cm")
    if direction is None or isinstance(distance, bool):
        return None
    if not isinstance(distance, (int, float)) or distance <= 0:
        return None
    args = {"direction": direction}
    envelope = call_tool("read_lidar", args, registry)
    need = float(distance) + RECHECK_MARGIN_CM
    details: dict[str, Any] = {
        "direction": direction,
        "requested_cm": distance,
        "margin_cm": RECHECK_MARGIN_CM,
        "required_cm": need,
        "lidar_result": envelope,
    }
    if not envelope["ok"]:
        message = envelope["error"]["message"]
        details.update(passed=False, reason=f"recheck read failed: {message}")
        return RecheckResult(
            details,
            f"Move cancelled: {RECHECK_PHRASE}. The {direction} LiDAR could not be read "
            f"({message}), so the path cannot be confirmed clear. The robot did not move. "
            "Report this and that the move was cancelled.",
        )
    reading = envelope["data"]
    value = reading.get("value")
    details["reading_cm"] = value
    usable = isinstance(value, (int, float)) and reading.get("status") in (
        "clear",
        "blocked",
    )
    if not usable:
        details.update(passed=False, reason="recheck reading is not usable")
        return RecheckResult(
            details,
            f"Move cancelled: {RECHECK_PHRASE}. The {direction} LiDAR returned an unusable "
            f"reading (status {reading.get('status')}). The robot did not move. Report this "
            "and that the move was cancelled.",
        )
    if value < need:
        details.update(
            passed=False, reason="reading below requested distance plus margin"
        )
        return RecheckResult(
            details, _cancel_message(direction, reading, need, float(distance))
        )
    details.update(passed=True)
    return RecheckResult(details)
