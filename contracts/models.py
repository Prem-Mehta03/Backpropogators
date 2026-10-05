"""Strict Pydantic models for data that crosses project layer boundaries."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Perspective = Literal["user", "agent_sensor", "historical", "third_party"]
BeliefStatus = Literal["active", "superseded", "disputed"]
SensorStatus = Literal["clear", "blocked", "unknown", "error"]
ErrorCode = Literal[
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "CONFLICT",
    "SENSOR_UNAVAILABLE",
    "STORAGE_ERROR",
    "STEP_LIMIT",
    "INTERNAL",
]
BeliefValue = str | int | float | bool
SensorValue = str | int | float | dict[str, Any]


def _check_utc_timestamp(value: str) -> str:
    """Require an ISO 8601 UTC timestamp with the contract's trailing Z."""
    if not value.endswith("Z"):
        raise ValueError("timestamp must be ISO 8601 UTC and end with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO 8601") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must use UTC")
    return value


def _check_json_value(value: Any) -> Any:
    """Reject Python-only and non-finite values from JSON contract payloads."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, list):
        for item in value:
            _check_json_value(item)
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            _check_json_value(item)
        return value
    raise ValueError(f"value is not JSON-compatible: {type(value).__name__}")


class ContractModel(BaseModel):
    """Base model that rejects undeclared fields and implicit type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Belief(ContractModel):
    """A sourced claim with confidence, perspective, status, and validity."""

    schema_version: Literal["1.0"]
    belief_id: str = Field(pattern=r"^b_\d{6}$")
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: BeliefValue
    source: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: str
    perspective: Perspective
    status: BeliefStatus
    valid_from: str
    valid_to: str | None
    supersedes: str | None

    @field_validator("timestamp", "valid_from")
    @classmethod
    def validate_required_timestamps(cls, value: str) -> str:
        """Validate required UTC timestamp fields."""
        return _check_utc_timestamp(value)

    @field_validator("valid_to")
    @classmethod
    def validate_optional_timestamp(cls, value: str | None) -> str | None:
        """Validate a non-null validity end timestamp."""
        return _check_utc_timestamp(value) if value is not None else None

    @field_validator("subject", "predicate")
    @classmethod
    def validate_nonempty_identifiers(cls, value: str) -> str:
        """Reject identifiers that contain only whitespace."""
        if not value.strip():
            raise ValueError("subject and predicate must be non-empty")
        return value

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        """Require non-null provenance sources to contain a name."""
        if value is not None and not value.strip():
            raise ValueError("source must be a non-empty string or null")
        return value

    @field_validator("object")
    @classmethod
    def validate_object_value(cls, value: BeliefValue) -> BeliefValue:
        """Reject non-finite numbers in claim values."""
        return _check_json_value(value)

    @field_validator("supersedes")
    @classmethod
    def validate_superseded_id(cls, value: str | None) -> str | None:
        """Require referenced belief IDs to use the contract format."""
        if value is not None and re.fullmatch(r"b_\d{6}", value) is None:
            raise ValueError("supersedes must match b_ followed by six digits")
        return value

    @model_validator(mode="after")
    def validate_validity_window(self) -> Belief:
        """Require active beliefs to remain valid and superseded beliefs to be closed."""
        if self.status == "active" and self.valid_to is not None:
            raise ValueError("active beliefs must have valid_to=null")
        if self.status == "superseded" and self.valid_to is None:
            raise ValueError("superseded beliefs require valid_to")
        return self


class SensorReading(ContractModel):
    """A sensor observation represented as JSON-compatible data."""

    schema_version: Literal["1.0"]
    sensor: str = Field(min_length=1)
    value: SensorValue
    unit: str | None
    status: SensorStatus
    timestamp: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        """Validate the sensor observation time."""
        return _check_utc_timestamp(value)

    @field_validator("value")
    @classmethod
    def validate_sensor_value(cls, value: SensorValue) -> SensorValue:
        """Require the observation value to be finite JSON-compatible data."""
        return _check_json_value(value)


class ToolError(ContractModel):
    """A fixed-code error returned inside a ToolResult envelope."""

    code: ErrorCode
    message: str
    retryable: bool


class ToolResult(ContractModel):
    """Standard result envelope returned by declarative and sensorimotor APIs."""

    schema_version: Literal["1.0"]
    tool: str = Field(min_length=1)
    ok: bool
    data: Any
    error: ToolError | None
    timestamp: str

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        """Validate the envelope creation time."""
        return _check_utc_timestamp(value)

    @field_validator("data")
    @classmethod
    def validate_data_is_json(cls, value: Any) -> Any:
        """Ensure the envelope data can cross the boundary as JSON."""
        return _check_json_value(value)

    @model_validator(mode="after")
    def validate_result_shape(self) -> ToolResult:
        """Keep success and failure payloads mutually consistent."""
        if self.ok and self.error is not None:
            raise ValueError("successful results must have error=null")
        if not self.ok and (self.error is None or self.data is not None):
            raise ValueError("failed results require an error and data=null")
        return self
