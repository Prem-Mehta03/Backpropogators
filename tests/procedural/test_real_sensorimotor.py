"""The procedural layer running against Asvin's real simulated world (sensorimotor/).

Skipped automatically if sensorimotor/ does not provide create_sensorimotor on this branch.
Memory is Vyom's real BeliefMemory when present, otherwise the fake (only the tools differ).
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from procedural.agent import run_agent
from procedural.tools import call_tool
from scripts.tool_wiring import (
    DEFAULT_SCENARIO,
    SENSOR_TOOLS,
    SENSORIMOTOR_SOURCE,
    build_tool_registry,
)
from tests.procedural.scripted_llm import ScriptedLLM, call, say

_module = importlib.import_module("sensorimotor")
pytestmark = pytest.mark.skipif(
    not hasattr(_module, "create_sensorimotor"), reason="sensorimotor layer not on this branch"
)

QUESTION = "Is your route clear? Justify your response by inspecting your internal system layers."


def _registry() -> tuple[dict[str, Any], dict[str, str]]:
    return build_tool_registry()


def test_all_six_sensor_tools_come_from_the_real_world() -> None:
    _, sources = _registry()
    assert all(sources[name] == SENSORIMOTOR_SOURCE for name in SENSOR_TOOLS)


def test_lidar_reading_is_a_valid_sensor_reading_envelope() -> None:
    registry, _ = _registry()
    out = call_tool("read_lidar", {}, registry)
    assert out["ok"] is True
    reading = out["data"]
    assert reading["sensor"] and 0.0 <= reading["confidence"] <= 1.0
    assert reading["status"] in {"clear", "blocked", "unknown", "error"}


def test_position_reports_x_y_and_heading() -> None:
    registry, _ = _registry()
    out = call_tool("get_position", {}, registry)
    assert out["ok"] is True
    assert {"x", "y", "heading_deg"} <= set(out["data"]["value"])


def test_moving_changes_the_position() -> None:
    registry, _ = _registry()
    before = call_tool("get_position", {}, registry)["data"]["value"]
    assert call_tool("move_forward", {"distance_cm": 5}, registry)["ok"] is True
    after = call_tool("get_position", {}, registry)["data"]["value"]
    assert (before["x"], before["y"]) != (after["x"], after["y"])


def test_turn_beyond_360_degrees_is_rejected_by_the_layer() -> None:
    registry, _ = _registry()
    out = call_tool("turn", {"degrees": 400}, registry)
    assert out["ok"] is False and out["error"]["code"] == "INVALID_ARGUMENT"


def test_each_registry_gets_its_own_fresh_world() -> None:
    first, _ = _registry()
    start = call_tool("get_position", {}, first)["data"]["value"]
    call_tool("move_forward", {"distance_cm": 5}, first)
    second, _ = _registry()
    assert call_tool("get_position", {}, second)["data"]["value"] == start


def test_unknown_scenario_is_reported_with_its_name() -> None:
    with pytest.raises(RuntimeError, match="no_such_scenario"):
        build_tool_registry(scenario="no_such_scenario")


def test_scenario_a_end_to_end_with_real_memory_and_real_sensors() -> None:
    registry, sources = _registry()
    # Read what this scenario's LiDAR says from a twin world, so the scripted model repeats the
    # real sensor name and value instead of a guess.
    twin, _ = build_tool_registry(scenario=DEFAULT_SCENARIO)
    lidar = call_tool("read_lidar", {}, twin)["data"]
    map_belief = call_tool("query_belief", {"subject": "path_A"}, registry)["data"][0]
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("read_lidar", {}, "c2"),
            call(
                "downgrade_belief",
                {
                    "belief_id": map_belief["belief_id"],
                    "new_confidence": 0.2,
                    "reason": "Live LiDAR contradicts the map",
                },
                "c3",
            ),
            call(
                "update_belief",
                {
                    "subject": "path_A",
                    "predicate": "status",
                    "object": lidar["status"],
                    "source": lidar["sensor"],
                    "confidence": lidar["confidence"],
                    "perspective": "agent_sensor",
                    "reason": "Live LiDAR reading",
                },
                "c4",
            ),
            say(f"No. The map said clear, but the LiDAR reads {lidar['status']}."),
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    assert out.finished and out.error is None and out.evidence_nudges == 0
    assert out.tool_calls[1]["result"]["data"]["sensor"] == lidar["sensor"]
    assert all(c["result"]["ok"] for c in out.tool_calls), out.tool_calls
    assert "guard" not in out.tool_calls[3]
    assert sources["read_lidar"] == SENSORIMOTOR_SOURCE
