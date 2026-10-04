"""The ONLY module in this layer that touches the contract models.

Everything else in ``sensorimotor/`` works with plain Python values and calls
the three builders below. When Vyom's ``contracts/`` package changes (or lands
for real), this is the only file that may need editing.

Placeholders for later (search for ``TODO(contract)``):
  * the real constant name in ``contracts/version.py``
  * whether the real models expose ``model_dump`` the same way
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_log = logging.getLogger(__name__)

try:  # real package from Vyom
    from contracts.models import SensorReading, ToolError, ToolResult

    try:  # TODO(contract): confirm constant name in contracts/version.py
        from contracts.version import SCHEMA_VERSION
    except (ImportError, AttributeError):
        SCHEMA_VERSION = "1.0"
    USING_SHIM = False
except ModuleNotFoundError:  # temporary local stand-in (never committed)
    try:
        from dev_shim.contracts_shim import (
            SCHEMA_VERSION,
            SensorReading,
            ToolError,
            ToolResult,
        )
    except ModuleNotFoundError as exc:
        raise ImportError(
            "sensorimotor needs Vyom's contracts/ package (contracts/models.py). "
            "It is not on this branch yet: pull main once it lands, or use the local "
            "dev_shim/ placeholder."
        ) from exc

    USING_SHIM = True
    _log.warning("Using TEMPORARY local contract shim (contracts/ not found).")

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

    Never escapes the layer: ``run_tool`` converts it into a ToolResult.
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


def success(tool: str, data: Any, timestamp: str) -> ToolResult:
    """Build a success ToolResult envelope (Guidelines 4.4)."""
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool=tool,
        ok=True,
        data=data,
        error=None,
        timestamp=timestamp,
    )


def failure(tool: str, code: str, message: str, retryable: bool, timestamp: str) -> ToolResult:
    """Build an error ToolResult envelope. ``code`` must be from the fixed list."""
    if code not in ERROR_CODES:
        code, message = "INTERNAL", f"Unknown error code requested: {code}"
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool=tool,
        ok=False,
        data=None,
        error=ToolError(code=code, message=message, retryable=retryable),
        timestamp=timestamp,
    )


def dump(result: ToolResult) -> dict[str, Any]:
    """Plain-JSON dict of a validated envelope."""
    return result.model_dump(mode="json")


def run_tool(tool: str, now_iso: Callable[[], str], body: Callable[[], Any]) -> dict[str, Any]:
    """Run ``body`` and always return a validated envelope DICT; never raise.

    Returns a dict (not a model) to match the procedural layer's convention
    ("every result is a validated ToolResult envelope dict"): it stays valid
    even if the consumer's ToolResult class is a different object than ours.

    ``body`` returns the data payload (usually a SensorReading) or raises
    ToolFailure. Any other exception becomes INTERNAL.
    """
    try:
        return dump(success(tool, body(), now_iso()))
    except ToolFailure as exc:
        return dump(failure(tool, exc.code, exc.message, exc.retryable, now_iso()))
    except Exception as exc:  # noqa: BLE001 - boundary must not leak exceptions
        _log.exception("Unexpected error in tool %s", tool)
        return dump(failure(tool, "INTERNAL", f"{type(exc).__name__}: {exc}", False, now_iso()))
