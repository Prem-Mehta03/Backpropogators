"""T06: a route question needs get_belief_history, because query_belief hides superseded beliefs.

Live T06 failed 0/3: the model called only query_belief and read_lidar, saw only the newest
active belief and never learned that an older map entry had been replaced, so it never called it
stale. These tests run the real memory with a stale entry and a scripted model.
"""

from __future__ import annotations

from typing import Any

from procedural.agent import run_agent
from procedural.checklist import missing_evidence
from scripts.tool_wiring import build_memory, build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say

QUESTION = "Is your route clear? Justify your response by inspecting your internal system layers."
STALE_ANSWER = (
    "Yes, the route is clear. The newer floor_plan_rev2 plan says clear and the LiDAR agrees. "
    "The 2026-09-01 default_map entry saying blocked is stale and outdated."
)


def _stale_registry() -> tuple[dict[str, Any], Any]:
    memory = build_memory(seed=False)
    memory.add_belief(
        "path_A",
        "status",
        "blocked",
        "default_map",
        1.0,
        "historical",
        "2026-09-01T09:00:00Z",
    )
    memory.update_belief(
        "path_A",
        "status",
        "clear",
        "floor_plan_rev2",
        0.9,
        "historical",
        "revised floor plan",
        "2026-10-02T09:16:00Z",
    )
    registry, _ = build_tool_registry(memory=memory, real_sensors=False)
    return registry, memory


def test_query_belief_alone_hides_the_stale_entry_but_history_shows_it() -> None:
    _, memory = _stale_registry()
    current = memory.query_belief("path_A")["data"]
    assert [b["source"] for b in current] == ["floor_plan_rev2"]
    history = memory.get_belief_history("path_A", "status")["data"]
    old = next(b for b in history if b["source"] == "default_map")
    assert old["status"] == "superseded" and old["valid_to"] is not None


def test_a_route_answer_is_refused_until_the_history_was_read() -> None:
    registry, _ = _stale_registry()
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "q"),
            call("read_lidar", {}, "l"),
            say("Yes, the route is clear."),  # what the live model did: no history
            call("get_belief_history", {"subject": "path_A"}, "h"),
            say(STALE_ANSWER),
        ]
    )
    out = run_agent(QUESTION, llm, registry)
    assert out.finished and out.evidence_nudges == 1
    assert "get_belief_history" in llm.seen[3][-1]["content"]
    history = next(c for c in out.tool_calls if c["tool"] == "get_belief_history")
    assert any(b["status"] == "superseded" for b in history["result"]["data"])
    assert "stale" in out.answer and "2026-09-01" in out.answer


def test_history_of_another_subject_does_not_satisfy_a_route_question() -> None:
    log = [
        {
            "tool": "query_belief",
            "args": {"subject": "path_A"},
            "result": {"ok": True, "data": []},
        },
        {"tool": "read_lidar", "args": {}, "result": {"ok": True, "data": {}}},
        {
            "tool": "get_belief_history",
            "args": {"subject": "box_01"},
            "result": {"ok": True, "data": []},
        },
    ]
    registered = ("query_belief", "get_belief_history", "read_lidar")
    assert missing_evidence(log, (("query_belief",), ("read_lidar",)), registered) == []
    from procedural.checklist import DEFAULT_REQUIRED_EVIDENCE

    assert missing_evidence(log, DEFAULT_REQUIRED_EVIDENCE, registered) == [
        "get_belief_history"
    ]


def test_other_questions_and_registries_without_history_are_unaffected() -> None:
    from procedural.checklist import DEFAULT_REQUIRED_EVIDENCE

    box = [
        {
            "tool": "query_belief",
            "args": {"subject": "box_01"},
            "result": {"ok": True, "data": []},
        },
        {"tool": "read_camera", "args": {}, "result": {"ok": True, "data": {}}},
    ]
    assert (
        missing_evidence(
            box,
            DEFAULT_REQUIRED_EVIDENCE,
            ("query_belief", "read_camera", "get_belief_history"),
        )
        == []
    )
    route = [
        {
            "tool": "query_belief",
            "args": {"subject": "path_A"},
            "result": {"ok": True, "data": []},
        },
        {"tool": "read_lidar", "args": {}, "result": {"ok": True, "data": {}}},
    ]
    assert (
        missing_evidence(
            route, DEFAULT_REQUIRED_EVIDENCE, ("query_belief", "read_lidar")
        )
        == []
    )
