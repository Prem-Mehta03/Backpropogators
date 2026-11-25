"""Shared JSON contracts for I, Agent."""

from .models import Belief, Perspective, SensorReading, ToolError, ToolResult
from .version import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "Belief",
    "Perspective",
    "SensorReading",
    "ToolError",
    "ToolResult",
]
