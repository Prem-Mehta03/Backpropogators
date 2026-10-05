"""Tool wrappers: schemas match the contract, arguments are validated, nothing raises."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.models import Belief, SensorReading, ToolResult
from procedural.tools import (
    SPECS_BY_NAME,
    TOOL_SCHEMAS,
    call_tool,
    error_result,
    validate_arguments,
)
from scripts.tool_wiring import build_tool_registry

REGISTRY, _ = build_tool_registry(use_real=False)

# Guidelines 4.5: tool -> (all argument names, required argument names)
CONTRACT = {
    "query_belief": ({"subject", "predicate", "perspective"}, {"subject"}),
    "get_belief_history": ({"subject", "predicate"}, {"subject"}),
    "update_belief": (
        {"subject", "predicate", "object", "source", "confidence", "perspective", "reason"},
        {"subject", "predicate", "object", "source", "confidence", "perspective", "reason"},
    ),
    "downgrade_belief": (
        {"belief_id", "new_confidence", "reason"},
        {"belief_id", "new_confidence", "reason"},
    ),
    "detect_conflict": ({"subject", "predicate"}, {"subject", "predicate"}),
    "read_lidar": ({"direction"}, set()),
    "read_camera": ({"target"}, set()),
    "get_position": (set(), set()),
    "move_forward": ({"distance_cm"}, {"distance_cm"}),
    "move_backward": ({"distance_cm"}, {"distance_cm"}),
    "turn": ({"degrees"}, {"degrees"}),
}

VALID_ARGS: dict[str, dict[str, Any]] = {
    "query_belief": {"subject": "path_A", "predicate": "status"},
    "get_belief_history": {"subject": "path_A"},
    "update_belief": {
        "subject": "path_A",
        "predicate": "status",
        "object": "blocked",
        "source": "lidar_front",
        "confidence": 0.98,
        "perspective": "agent_sensor",
        "reason": "live reading",
    },
    "downgrade_belief": {"belief_id": "b_000123", "new_confidence": 0.3, "reason": "conflict"},
    "detect_conflict": {"subject": "path_A", "predicate": "status"},
    "read_lidar": {},
    "read_camera": {"target": "box_01"},
    "get_position": {},
    "move_forward": {"distance_cm": 10},
    "move_backward": {"distance_cm": 5.5},
    "turn": {"degrees": -90},
}


def test_every_contract_tool_has_a_schema_with_exact_argument_names() -> None:
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in TOOL_SCHEMAS}
    assert set(schemas) == set(CONTRACT)
    for name, (all_args, required) in CONTRACT.items():
        assert set(schemas[name]["properties"]) == all_args, name
        assert set(schemas[name]["required"]) == required, name


def test_schemas_are_json_serialisable_objects() -> None:
    for schema in TOOL_SCHEMAS:
        json.dumps(schema)
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"
        assert schema["function"]["description"]


@pytest.mark.parametrize("name", sorted(CONTRACT))
def test_valid_call_reaches_the_stub_and_returns_a_valid_envelope(name: str) -> None:
    out = call_tool(name, VALID_ARGS[name], REGISTRY)
    assert out["tool"] == name
    assert out["ok"] is True, out["error"]
    ToolResult.model_validate(out)


def test_stub_data_conforms_to_the_contract_models() -> None:
    for name in ("query_belief", "get_belief_history", "update_belief", "downgrade_belief"):
        data = call_tool(name, VALID_ARGS[name], REGISTRY)["data"]
        for item in data if isinstance(data, list) else [data]:
            Belief.model_validate(item)
    for name in ("read_lidar", "read_camera", "get_position", "move_forward", "turn"):
        SensorReading.model_validate(call_tool(name, VALID_ARGS[name], REGISTRY)["data"])


@pytest.mark.parametrize(
    ("name", "args", "fragment"),
    [
        ("query_belief", {}, "missing required"),
        ("query_belief", {"subject": "path_A", "colour": "x"}, "unknown argument"),
        ("query_belief", {"subject": 5}, "type string"),
        ("query_belief", {"subject": "  "}, "must not be empty"),
        ("query_belief", {"subject": "a", "perspective": "narrator"}, "one of"),
        ("downgrade_belief", {"belief_id": "123", "new_confidence": 0.1, "reason": "r"}, "pattern"),
        (
            "downgrade_belief",
            {"belief_id": "b_000123", "new_confidence": 1.5, "reason": "r"},
            "at most",
        ),
        (
            "downgrade_belief",
            {"belief_id": "b_000123", "new_confidence": -0.1, "reason": "r"},
            "at least",
        ),
        (
            "downgrade_belief",
            {"belief_id": "b_000123", "new_confidence": True, "reason": "r"},
            "type number",
        ),
        ("move_forward", {"distance_cm": 0}, "greater than"),
        ("move_forward", {"distance_cm": "ten"}, "type number"),
        ("turn", {"degrees": None}, "type number"),
        ("read_lidar", {"direction": 5}, "type string"),
        ("get_position", {"extra": 1}, "unknown argument"),
    ],
)
def test_bad_arguments_are_invalid_argument_with_a_readable_message(
    name: str, args: dict[str, Any], fragment: str
) -> None:
    out = call_tool(name, args, REGISTRY)
    assert out["ok"] is False and out["error"]["code"] == "INVALID_ARGUMENT"
    assert fragment in out["error"]["message"]


def test_update_belief_object_accepts_string_number_and_boolean() -> None:
    spec = SPECS_BY_NAME["update_belief"]
    for value in ("red", 12, 0.5, True):
        validate_arguments(spec, {**VALID_ARGS["update_belief"], "object": value})
    with pytest.raises(ValueError):
        validate_arguments(spec, {**VALID_ARGS["update_belief"], "object": ["x"]})


def test_only_supplied_arguments_are_passed_so_layer_defaults_apply() -> None:
    seen: dict[str, Any] = {}

    def recorder(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return REGISTRY["read_lidar"]()

    call_tool("read_lidar", {}, {"read_lidar": recorder})
    assert seen == {}


def test_unknown_tool_is_invalid_argument() -> None:
    out = call_tool("fly", {}, REGISTRY)
    assert out["ok"] is False and out["error"]["code"] == "INVALID_ARGUMENT"


def test_known_tool_that_is_not_connected_is_internal() -> None:
    out = call_tool("read_lidar", {}, {})
    assert out["error"]["code"] == "INTERNAL" and "not connected" in out["error"]["message"]


def test_error_envelope_from_the_layer_passes_through_unchanged() -> None:
    out = call_tool("query_belief", {"subject": "nothing_here"}, REGISTRY)
    assert out["ok"] is False and out["error"]["code"] == "NOT_FOUND" and out["data"] is None


def test_exceptions_and_invalid_envelopes_become_internal() -> None:
    def boom(**_: Any) -> dict[str, Any]:
        raise RuntimeError("x")

    assert call_tool("read_lidar", {}, {"read_lidar": boom})["error"]["code"] == "INTERNAL"
    assert (
        call_tool("read_lidar", {}, {"read_lidar": lambda **_: {"nope": 1}})["error"]["code"]
        == "INTERNAL"
    )


def test_envelope_naming_a_different_tool_is_internal() -> None:
    wrong = {"read_lidar": lambda **_: REGISTRY["get_position"]()}
    out = call_tool("read_lidar", {}, wrong)
    assert out["error"]["code"] == "INTERNAL" and "get_position" in out["error"]["message"]


def test_error_result_is_a_valid_envelope_and_rejects_unknown_codes() -> None:
    out = error_result("read_lidar", "SENSOR_UNAVAILABLE", "offline", retryable=True)
    assert ToolResult.model_validate(out).error.retryable is True  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        error_result("read_lidar", "MADE_UP_CODE", "x")


def _properties(name: str) -> dict[str, Any]:
    schema = next(x for x in TOOL_SCHEMAS if x["function"]["name"] == name)
    return schema["function"]["parameters"]["properties"]


def test_query_belief_descriptions_steer_the_model_away_from_the_route_mistake() -> None:
    props = _properties("query_belief")
    assert "Exact entity id" in props["subject"]["description"]
    assert "never a description" in props["subject"]["description"]
    for optional in ("predicate", "perspective"):
        assert "Leave it out" in props[optional]["description"]
        assert "hides beliefs that exist" in props[optional]["description"]
    description = next(x for x in TOOL_SCHEMAS if x["function"]["name"] == "query_belief")
    assert "NOT_FOUND" in description["function"]["description"]


def test_every_memory_tool_asks_for_an_exact_entity_id() -> None:
    for name in ("query_belief", "get_belief_history", "update_belief", "detect_conflict"):
        assert "Exact entity id" in _properties(name)["subject"]["description"], name
