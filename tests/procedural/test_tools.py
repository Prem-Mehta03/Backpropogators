"""Tool wrapper: schema matches the contract, arguments are validated, nothing raises."""

from __future__ import annotations

from typing import Any

from contracts.models import ToolResult
from procedural.tools import TOOL_SCHEMAS, call_tool, error_result
from sensorimotor import stub

REGISTRY = {"read_lidar": stub.read_lidar}


def test_schema_uses_contract_tool_and_argument_names() -> None:
    fn = TOOL_SCHEMAS[0]["function"]
    assert fn["name"] == "read_lidar"
    assert list(fn["parameters"]["properties"]) == ["direction"]
    assert fn["parameters"]["required"] == []


def test_stub_is_the_scenario_a_fixture() -> None:
    res = ToolResult.model_validate(stub.read_lidar())
    assert res.ok and res.data["value"] == 12 and res.data["status"] == "blocked"


def test_default_direction_works() -> None:
    out = call_tool("read_lidar", {}, REGISTRY)
    assert out["ok"] is True and out["data"]["sensor"] == "lidar_front"


def test_bad_arguments_and_unknown_tool_are_invalid_argument() -> None:
    for name, args in [
        ("read_lidar", {"direction": 5}),
        ("read_lidar", {"angle": 90}),
        ("fly", {}),
    ]:
        out = call_tool(name, args, REGISTRY)
        assert out["ok"] is False and out["error"]["code"] == "INVALID_ARGUMENT"


def test_error_envelope_from_the_layer_is_passed_through() -> None:
    out = call_tool("read_lidar", {"direction": "left"}, REGISTRY)
    assert out["ok"] is False and out["error"]["code"] == "INVALID_ARGUMENT"
    assert out["data"] is None


def test_exceptions_and_invalid_envelopes_become_internal() -> None:
    def boom(direction: str = "front") -> dict[str, Any]:
        raise RuntimeError("x")

    assert call_tool("read_lidar", {}, {"read_lidar": boom})["error"]["code"] == "INTERNAL"
    bad = {"read_lidar": lambda direction="front": {"nope": 1}}
    assert call_tool("read_lidar", {}, bad)["error"]["code"] == "INTERNAL"


def test_error_result_is_a_valid_envelope() -> None:
    out = error_result("read_lidar", "SENSOR_UNAVAILABLE", "offline", retryable=True)
    assert ToolResult.model_validate(out).error.retryable is True
