"""LLM tool wrappers (Day 1: read_lidar only).

Same tool and argument names as Guidelines 4.5. The registry is injected, so swapping the
stub for Asvin's real function is a one-line change. Every result is a validated
ToolResult envelope dict; nothing raises across the boundary.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from contracts.models import ToolResult

logger = logging.getLogger(__name__)

ToolFn = Callable[..., dict[str, Any]]

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_lidar",
            "description": (
                "Read the live LiDAR distance sensor. Returns a SensorReading with value "
                "(cm), status (clear/blocked/unknown/error), timestamp and confidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "Sensor direction. Defaults to 'front'.",
                    }
                },
                "required": [],
            },
        },
    }
]


def error_result(tool: str, code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    """Build a validated ToolResult error envelope (Guidelines 4.4).

    Inputs: tool name, error code from the fixed list, message, retryable flag.
    Output: envelope dict with ok=false. Raises pydantic ValidationError on an unknown code.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ToolResult(
        tool=tool,
        ok=False,
        data=None,
        error={"code": code, "message": message, "retryable": retryable},
        timestamp=now,
    ).model_dump()


def _validate_read_lidar(args: dict[str, Any]) -> str:
    unknown = set(args) - {"direction"}
    if unknown:
        raise ValueError(f"unknown argument(s): {sorted(unknown)}")
    direction = args.get("direction", "front")
    if not isinstance(direction, str):
        raise ValueError("direction must be a string")
    return direction


def call_tool(name: str, args: dict[str, Any], registry: dict[str, ToolFn]) -> dict[str, Any]:
    """Validate arguments, call the registered function, validate the envelope.

    Inputs: tool name, argument dict, registry of name -> function.
    Output: ToolResult envelope dict. Error codes: INVALID_ARGUMENT (unknown tool or bad
    args), INTERNAL (function raised or returned an invalid envelope).
    """
    fn = registry.get(name)
    if fn is None:
        return error_result(name, "INVALID_ARGUMENT", f"Unknown tool: {name}")
    try:
        if name == "read_lidar":
            result = fn(direction=_validate_read_lidar(args))
        else:  # tools are added one by one in week 3
            return error_result(name, "INVALID_ARGUMENT", f"No wrapper for tool: {name}")
    except ValueError as exc:
        return error_result(name, "INVALID_ARGUMENT", str(exc))
    except Exception as exc:  # layers must not raise across the boundary
        logger.exception("Tool %s raised", name)
        return error_result(name, "INTERNAL", f"{type(exc).__name__}: {exc}")
    try:
        return ToolResult.model_validate(result).model_dump()
    except Exception as exc:
        return error_result(name, "INTERNAL", f"Invalid envelope from {name}: {exc}")
