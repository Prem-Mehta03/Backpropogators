"""LLM tool wrappers: one table describes every tool, schemas and validation come from it.

Tool names and argument names are exactly those in Guidelines 4.5. The tool functions
themselves live in other layers and are passed in as a registry (name -> function), so
this module imports nothing from declarative/ or sensorimotor/. Every result is a validated
ToolResult envelope dict; nothing raises across the boundary (Guidelines 4.4).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from contracts.models import ToolResult

logger = logging.getLogger(__name__)

ToolFn = Callable[..., dict[str, Any]]

SCHEMA_VERSION = "1.0"  # contract v1.0, required on every ToolResult
PERSPECTIVES = ("user", "agent_sensor", "historical", "third_party")
BELIEF_ID_PATTERN = r"^b_\d{6}$"


@dataclass(frozen=True)
class Param:
    """One tool argument. `json_types` uses JSON-schema names: string, number, boolean."""

    name: str
    json_types: tuple[str, ...]
    description: str
    required: bool = False
    enum: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: float | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call: name, what it does, and its arguments."""

    name: str
    description: str
    params: tuple[Param, ...] = ()


def _str(name: str, description: str, required: bool = False, **kw: Any) -> Param:
    return Param(name, ("string",), description, required, **kw)


def _num(name: str, description: str, required: bool = False, **kw: Any) -> Param:
    return Param(name, ("number",), description, required, **kw)


_PERSPECTIVE_HELP = "Whose view this is: user, agent_sensor, historical or third_party."
_SUBJECT_HELP = (
    "Exact entity id, for example path_A, box_01 or robot. Use an id from the entity list in "
    "the system prompt, never a description such as 'route'."
)
_FILTER_WARNING = "A wrong value hides beliefs that exist."
_NOT_FOUND_HINT = (
    "If this returns NOT_FOUND or an empty list, the id or a filter may be wrong: retry once "
    "with an id from the entity list and no filters."
)

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "query_belief",
        "Look up stored beliefs about a subject. Returns a list of beliefs, each with "
        "source, confidence, timestamp, perspective and status. " + _NOT_FOUND_HINT,
        (
            _str("subject", _SUBJECT_HELP, True),
            _str(
                "predicate",
                "Optional filter, for example status or color. Leave it out on the first "
                "lookup. " + _FILTER_WARNING,
            ),
            _str(
                "perspective",
                "Optional filter: user, agent_sensor, historical or third_party. Leave it out "
                "unless the user asked for one viewpoint. " + _FILTER_WARNING,
                enum=PERSPECTIVES,
            ),
        ),
    ),
    ToolSpec(
        "get_belief_history",
        "Return every stored belief about a subject, oldest first, including superseded ones. "
        + _NOT_FOUND_HINT,
        (
            _str("subject", _SUBJECT_HELP, True),
            _str(
                "predicate",
                "Optional filter, for example status. Leave it out on the first lookup. "
                + _FILTER_WARNING,
            ),
        ),
    ),
    ToolSpec(
        "update_belief",
        "Record a new belief in memory (the old one is superseded, never deleted). Use only "
        "for evidence you actually obtained from a tool or the user.",
        (
            _str("subject", _SUBJECT_HELP, True),
            _str("predicate", "Property or relation, for example status or color.", True),
            Param(
                "object",
                ("string", "number", "boolean"),
                "The claimed value, for example clear, red or 12.",
                True,
            ),
            _str("source", "Where the evidence came from, for example lidar_front or user.", True),
            _num("confidence", "Certainty from 0.0 to 1.0.", True, minimum=0.0, maximum=1.0),
            _str("perspective", _PERSPECTIVE_HELP, True, enum=PERSPECTIVES),
            _str("reason", "Why this update is being made.", True),
        ),
    ),
    ToolSpec(
        "downgrade_belief",
        "Lower the confidence of an existing belief, for example when a live reading "
        "contradicts it.",
        (
            _str("belief_id", "Id of the belief, like b_000123.", True, pattern=BELIEF_ID_PATTERN),
            _num("new_confidence", "New certainty, 0.0 to 1.0.", True, minimum=0.0, maximum=1.0),
            _str("reason", "Why the belief is being downgraded.", True),
        ),
    ),
    ToolSpec(
        "detect_conflict",
        "List stored beliefs about the same subject and predicate that contradict each other.",
        (
            _str("subject", _SUBJECT_HELP, True),
            _str("predicate", "Property, for example status.", True),
        ),
    ),
    ToolSpec(
        "read_lidar",
        "Read the live LiDAR distance sensor. Returns value (cm), status "
        "(clear, blocked, unknown or error), timestamp and confidence.",
        (_str("direction", "Sensor direction. Defaults to front."),),
    ),
    ToolSpec(
        "read_camera",
        "Read the live camera. Returns what it sees, for example an object id and colour.",
        (_str("target", "Optional object id to look at, for example box_01."),),
    ),
    ToolSpec("get_position", "Read the robot's current position and heading."),
    ToolSpec(
        "move_forward",
        "Move the robot forward. Returns the new position.",
        (
            _num(
                "distance_cm", "Distance in centimetres, greater than 0.", True, exclusive_minimum=0
            ),
        ),
    ),
    ToolSpec(
        "move_backward",
        "Move the robot backward. Returns the new position.",
        (
            _num(
                "distance_cm", "Distance in centimetres, greater than 0.", True, exclusive_minimum=0
            ),
        ),
    ),
    ToolSpec(
        "turn",
        "Turn the robot. Positive degrees turn one way, negative the other. Returns the "
        "new position.",
        (_num("degrees", "Angle in degrees.", True),),
    ),
)

SPECS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def _param_schema(param: Param) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": param.json_types[0] if len(param.json_types) == 1 else list(param.json_types),
        "description": param.description,
    }
    if param.enum is not None:
        schema["enum"] = list(param.enum)
    if param.minimum is not None:
        schema["minimum"] = param.minimum
    if param.maximum is not None:
        schema["maximum"] = param.maximum
    if param.exclusive_minimum is not None:
        schema["exclusiveMinimum"] = param.exclusive_minimum
    if param.pattern is not None:
        schema["pattern"] = param.pattern
    return schema


def build_schema(spec: ToolSpec) -> dict[str, Any]:
    """Turn a ToolSpec into the OpenAI-style tool schema the model sees."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": {
                "type": "object",
                "properties": {p.name: _param_schema(p) for p in spec.params},
                "required": [p.name for p in spec.params if p.required],
            },
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [build_schema(spec) for spec in TOOL_SPECS]


def error_result(tool: str, code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    """Build a validated ToolResult error envelope (Guidelines 4.4).

    Inputs: tool name, error code from the fixed list, message, retryable flag.
    Output: envelope dict with ok=false. Raises pydantic ValidationError on an unknown code.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "retryable": retryable},
        "timestamp": now,
    }
    return ToolResult.model_validate(envelope).model_dump()


def _is_type(value: Any, json_type: str) -> bool:
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "boolean":
        return isinstance(value, bool)
    if json_type == "number":  # bool is a subclass of int in Python; reject it explicitly
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _check_param(param: Param, value: Any) -> None:
    """Raise ValueError with a model-readable message if the value breaks the spec."""
    if not any(_is_type(value, t) for t in param.json_types):
        raise ValueError(f"{param.name} must be of type {' or '.join(param.json_types)}")
    if param.enum is not None and value not in param.enum:
        raise ValueError(f"{param.name} must be one of {list(param.enum)}")
    if isinstance(value, str) and param.pattern and not re.match(param.pattern, value):
        raise ValueError(f"{param.name} must match pattern {param.pattern}")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{param.name} must not be empty")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if param.minimum is not None and value < param.minimum:
            raise ValueError(f"{param.name} must be at least {param.minimum}")
        if param.maximum is not None and value > param.maximum:
            raise ValueError(f"{param.name} must be at most {param.maximum}")
        if param.exclusive_minimum is not None and value <= param.exclusive_minimum:
            raise ValueError(f"{param.name} must be greater than {param.exclusive_minimum}")


def validate_arguments(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
    """Check model-supplied arguments against the spec; return them unchanged if valid.

    Inputs: a ToolSpec and the parsed argument dict. Output: the same dict (only the
    arguments the model supplied, so the layer's own defaults still apply).
    Raises ValueError (message safe to show the model) on unknown, missing or bad arguments.
    """
    known = {p.name: p for p in spec.params}
    unknown = sorted(set(args) - set(known))
    if unknown:
        raise ValueError(f"unknown argument(s): {unknown}")
    missing = [p.name for p in spec.params if p.required and p.name not in args]
    if missing:
        raise ValueError(f"missing required argument(s): {missing}")
    for name, value in args.items():
        _check_param(known[name], value)
    return dict(args)


def call_tool(name: str, args: dict[str, Any], registry: dict[str, ToolFn]) -> dict[str, Any]:
    """Validate arguments, call the registered function, validate the envelope.

    Inputs: tool name, argument dict, registry of name -> function.
    Output: ToolResult envelope dict. Error codes: INVALID_ARGUMENT (unknown tool or bad
    args), INTERNAL (tool not registered, function raised, or invalid envelope returned).
    Errors reported by the layer itself (NOT_FOUND, SENSOR_UNAVAILABLE, ...) pass through.
    """
    spec = SPECS_BY_NAME.get(name)
    if spec is None:
        return error_result(name, "INVALID_ARGUMENT", f"Unknown tool: {name}")
    try:
        clean = validate_arguments(spec, args)
    except ValueError as exc:
        return error_result(name, "INVALID_ARGUMENT", str(exc))
    fn = registry.get(name)
    if fn is None:
        return error_result(name, "INTERNAL", f"Tool {name} is not connected")
    try:
        result = fn(**clean)
    except Exception as exc:  # layers must not raise across the boundary
        logger.exception("Tool %s raised", name)
        return error_result(name, "INTERNAL", f"{type(exc).__name__}: {exc}")
    try:
        envelope = ToolResult.model_validate(result).model_dump()
    except ValidationError as exc:
        return error_result(name, "INTERNAL", f"Invalid envelope from {name}: {exc}")
    if envelope["tool"] != name:
        return error_result(
            name, "INTERNAL", f"Envelope names tool {envelope['tool']!r}, expected {name!r}"
        )
    return envelope
