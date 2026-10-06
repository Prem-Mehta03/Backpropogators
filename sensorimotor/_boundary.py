"""The ONLY module in this layer that touches the contracts package.

Everything else in ``sensorimotor/`` works with plain Python values and calls
the builders below. The contract models, version constant and envelope helpers
all come from Vyom's ``contracts/`` package; nothing is redefined here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from contracts.models import SensorReading, ToolError, ToolResult
from contracts.validators import error_result, success_result
from contracts.version import SCHEMA_VERSION

__all__ = [
    "ERROR_CODES",
    "SCHEMA_VERSION",
    "SensorReading",
    "ToolError",
    "ToolFailure",
    "ToolResult",
    "build_reading",
    "failure",
    "run_tool",
]

_log = logging.getLogger(__name__)

ERROR_CODES = (
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "CONFLICT",
    "SENSOR_UNAVAILABLE",
    "STORAGE_ERROR",
    "STEP_LIMIT",
    "INTERNAL",
)


class ToolFailure(Exception):
    """Raised inside this layer to produce an error envelope.

    Never escapes the layer: ``run_tool`` converts it into a ToolResult dict.
    """

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def build_reading(
    sensor: str,
    value: Any,
    unit: str | None,
    status: str,
    timestamp: str,
    confidence: float,
) -> SensorReading:
    """Build and validate a SensorReading (Guidelines 4.3)."""
    return SensorReading(
        schema_version=SCHEMA_VERSION,
        sensor=sensor,
        value=value,
        unit=unit,
        status=status,
        timestamp=timestamp,
        confidence=confidence,
    )


def failure(tool: str, code: str, message: str, retryable: bool, timestamp: str) -> dict[str, Any]:
    """Build a validated error envelope dict. Unknown codes become INTERNAL."""
    if code not in ERROR_CODES:
        code, message = "INTERNAL", f"Unknown error code requested: {code}"
    return error_result(tool, code, message, retryable, timestamp)


def run_tool(tool: str, now_iso: Callable[[], str], body: Callable[[], Any]) -> dict[str, Any]:
    """Run ``body`` and always return a validated envelope DICT; never raise.

    ``body`` returns the data payload (usually a SensorReading) or raises
    ToolFailure. Any other exception becomes INTERNAL. The contract requires
    ``data`` to be plain JSON, so a model payload is dumped to a dict here.
    """
    try:
        payload = body()
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        return success_result(tool, payload, now_iso())
    except ToolFailure as exc:
        return failure(tool, exc.code, exc.message, exc.retryable, now_iso())
    except Exception as exc:  # noqa: BLE001 - boundary must not leak exceptions
        _log.exception("Unexpected error in tool %s", tool)
        return failure(tool, "INTERNAL", f"{type(exc).__name__}: {exc}", False, now_iso())
