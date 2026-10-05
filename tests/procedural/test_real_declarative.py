"""The procedural layer running against Vyom's real BeliefMemory (declarative/belief_graph.py).

Skipped automatically if the declarative layer is not on the branch. These tests always use the
fake sensors (real_sensors=False), so they cover the memory side only and do not depend on
Asvin's layer; test_real_sensorimotor.py covers the combination.
"""

from __future__ import annotations

from typing import Any

import pytest

from procedural.agent import run_agent
from procedural.tools import call_tool
from scripts.tool_wiring import (
    MEMORY_SOURCE,
    MEMORY_TOOLS,
    build_memory,
    build_tool_registry,
)
from tests.procedural.scripted_llm import ScriptedLLM, call, say

pytest.importorskip("declarative.belief_graph")

QUESTION = "Is your route clear? Justify your response by inspecting your internal system layers."


def _registry() -> tuple[dict[str, Any], dict[str, str], Any]:
    memory = build_memory()
    registry, sources = build_tool_registry(memory=memory, real_sensors=False)
    return registry, sources, memory


def test_memory_tools_come_from_the_real_class() -> None:
    _, sources, _ = _registry()
    assert all(sources[name] == MEMORY_SOURCE for name in MEMORY_TOOLS)


def test_seeded_map_belief_is_found_through_the_tool_wrapper() -> None:
    registry, _, _ = _registry()
    out = call_tool("query_belief", {"subject": "path_A"}, registry)
    assert out["ok"] is True
    (belief,) = out["data"]
    assert belief["object"] == "clear" and belief["source"] == "default_map"
    assert belief["confidence"] == 1.0 and belief["perspective"] == "historical"


def test_demo_beliefs_are_older_than_the_live_sensor_reading() -> None:
    registry, _, _ = _registry()
    for subject in ("path_A", "box_01"):
        for belief in call_tool("query_belief", {"subject": subject}, registry)["data"]:
            assert belief["timestamp"] == "2026-10-03T09:15:00Z"


def test_unknown_subject_gives_an_empty_ok_reply_not_a_crash() -> None:
    # Vyom's query_belief answers ok with no beliefs (not NOT_FOUND) when nothing matches.
    registry, _, _ = _registry()
    out = call_tool("query_belief", {"subject": "box_99"}, registry)
    assert out["ok"] is True and not out["data"]


def test_box_01_has_user_and_third_party_beliefs() -> None:
    registry, _, _ = _registry()
    out = call_tool("query_belief", {"subject": "box_01", "predicate": "color"}, registry)
    assert out["ok"] is True
    seen = {(b["perspective"], b["object"]) for b in out["data"]}
    assert {("user", "red"), ("third_party", "blue")} <= seen


def test_each_registry_gets_its_own_fresh_memory() -> None:
    first, _, _ = _registry()
    call_tool(
        "update_belief",
        {
            "subject": "path_A",
            "predicate": "status",
            "object": "blocked",
            "source": "lidar_front",
            "confidence": 0.98,
            "perspective": "agent_sensor",
            "reason": "test",
        },
        first,
    )
    second, _, _ = _registry()
    out = call_tool("query_belief", {"subject": "path_A"}, second)
    assert [b["object"] for b in out["data"]] == ["clear"]


def test_unseeded_memory_is_empty() -> None:
    registry, _ = build_tool_registry(memory=build_memory(seed=False), real_sensors=False)
    out = call_tool("query_belief", {"subject": "path_A"}, registry)
    assert out["ok"] is True and not out["data"]


def test_scenario_a_end_to_end_against_real_memory() -> None:
    registry, _, memory = _registry()
    map_id = memory.query_belief("path_A")["data"][0]["belief_id"]
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("read_lidar", {}, "c2"),
            call(
                "downgrade_belief",
                {"belief_id": map_id, "new_confidence": 0.5, "reason": "Live LiDAR contradicts"},
                "c3",
            ),
            call(
                "update_belief",
                {
                    "subject": "path_A",
                    "predicate": "status",
                    "object": "blocked",
                    "source": "lidar_front",
                    "confidence": 0.98,
                    "perspective": "agent_sensor",
                    "reason": "Live LiDAR reading",
                },
                "c4",
            ),
            say("No, the route is blocked. Map said clear (1.0); LiDAR reads 12 cm blocked."),
        ]
    )
    out = run_agent(QUESTION, llm, registry)

    assert out.finished and out.error is None and out.evidence_nudges == 0
    assert [c["tool"] for c in out.tool_calls] == [
        "query_belief",
        "read_lidar",
        "downgrade_belief",
        "update_belief",
    ]
    assert all(c["result"]["ok"] for c in out.tool_calls), out.tool_calls
    history = memory.get_belief_history("path_A", "status")["data"]
    assert history[0]["object"] == "clear" and len(history) >= 3  # original kept, never deleted
    current = memory.query_belief("path_A", "status")["data"]
    assert any(b["object"] == "blocked" and b["source"] == "lidar_front" for b in current)
    assert all(b["object"] != "clear" or b["confidence"] <= 0.5 for b in current)


def test_guard_still_refuses_a_made_up_belief_id_on_real_memory() -> None:
    registry, _, memory = _registry()
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("read_lidar", {}, "c2"),
            call(
                "downgrade_belief",
                {"belief_id": "b_999999", "new_confidence": 0.1, "reason": "guess"},
                "c3",
            ),
            say("Route is blocked."),
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    refused = out.tool_calls[2]
    assert refused["result"]["ok"] is False and "guard" in refused
    assert memory.query_belief("path_A")["data"][0]["confidence"] == 1.0
