"""Helpers for validating and serializing contract objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .models import ToolError, ToolResult
from .version import SCHEMA_VERSION

ModelT = TypeVar("ModelT", bound=BaseModel)


def utc_timestamp() -> str:
    """Return the current time as an ISO 8601 UTC timestamp ending in Z.

    Inputs: none. Output: UTC timestamp string. Errors: none expected.
    """
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def validate_contract(model: type[ModelT], payload: dict[str, Any]) -> ModelT:
    """Validate a mapping against a contract model.

    Inputs: Pydantic model class and payload mapping. Output: validated model instance.
    Errors: Pydantic ValidationError for invalid contract data.
    """
    return model.model_validate(payload)


def success_result(
    tool: str, data: Any, timestamp: str | None = None
) -> dict[str, Any]:
    """Build and validate a successful ToolResult envelope.

    Inputs: tool name, JSON-compatible data, and optional UTC timestamp. Output: a
    validated v1.0 success-envelope mapping. Errors: Pydantic ValidationError for an
    invalid tool name, timestamp, or result shape.
    """
    result = ToolResult(
        schema_version=SCHEMA_VERSION,
        tool=tool,
        ok=True,
        data=data,
        error=None,
        timestamp=timestamp or utc_timestamp(),
    )
    return result.model_dump(mode="json")


def error_result(
    tool: str,
    code: str,
    message: str,
    retryable: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build and validate a failed ToolResult envelope using a fixed error code.

    Inputs: tool name, fixed error code, message, retryable flag, and optional UTC
    timestamp. Output: a validated v1.0 failure-envelope mapping. Errors: Pydantic
    ValidationError for an unknown code or invalid field.
    """
    error = ToolError(code=code, message=message, retryable=retryable)
    result = ToolResult(
        schema_version=SCHEMA_VERSION,
        tool=tool,
        ok=False,
        data=None,
        error=error,
        timestamp=timestamp or utc_timestamp(),
    )
    return result.model_dump(mode="json")


def is_valid_contract(model: type[ModelT], payload: dict[str, Any]) -> bool:
    """Return whether a mapping validates against a contract model.

    Inputs: Pydantic model class and payload mapping. Output: validation boolean.
    Errors: returns False for Pydantic ValidationError; unrelated programming errors
    are not suppressed.
    """
    try:
        model.model_validate(payload)
    except ValidationError:
        return False
    return True
