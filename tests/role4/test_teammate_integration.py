"""Fresh canonical integration, fault observations and tamper checks; no hosted model."""
from copy import deepcopy
import json
import socket

import pytest
from pydantic import ValidationError

from contracts.models import Belief
from evaluation.role4.integration.canonical import canonical_timestamp, belief_view
from evaluation.role4.integration.offline import offline_guard
from evaluation.role4.integration.teammate_runner import run_teammate_case, trace_consistent, require_real_tools, verify_artifacts
from evaluation.role4.logger import read_events


@pytest.mark.parametrize("scenario", ["S01", "S02", "S03", "S07", "S08"])
def test_fresh_canonical_cases_keep_pending_answer_semantics(tmp_path, scenario):
    record = run_teammate_case(scenario, tmp_path / scenario)
    assert record["expectation_met"] and record["structured_answer_claims"] is None
    assert record["labels"]["human_semantic_review"] == "pending"
    assert record["labels"]["model_execution_mode"] == "scripted_llm"
    assert not any("tests.procedural.fakes" in source for source in record["tool_sources"].values())
    tools = [c["tool"] for c in record["agent"]["tool_calls"]]
    if scenario in ("S02", "S08"):
        assert tools.index("get_belief_history") < tools.index("update_belief")
    if scenario == "S03":
        assert tools.index("update_belief") < tools.index("get_belief_history")
        assert record["state_before"]["environment"]["lighting"]["name"] == "yellow"
        assert {b["source"] for b in record["state_after"]["memory"]["nodes"]} >= {"user", "bot_02", "camera_front"}
    if scenario == "S07":
        assert not record["labels"]["all_real_tools"]
        assert record["agent"]["error"]["code"] == "STEP_LIMIT"
        assert not any(d["dispatched"] for d in record["dispatch_outcomes"] if d["tool"] == "read_temperature")


@pytest.mark.parametrize("control", ["invalid_arguments", "malformed_arguments", "malformed_envelope", "missing_tool",
    "unavailable_evidence", "provenance_guard", "invented_downgrade", "confidence_override", "premature_answer", "step_limit", "llm_error", "downgrade"])
def test_real_layers_exercise_fault_guards_without_hiding_results(tmp_path, control):
    record = run_teammate_case("S07" if control == "unavailable_evidence" else "S01", tmp_path / control, control)
    assert record["evaluation"]["passed"] and record["expectation_met"]
    if control in ("invalid_arguments", "malformed_arguments", "provenance_guard", "invented_downgrade", "downgrade"):
        assert record["agent"]["error"] is None and record["agent"]["answer"]
    if control in ("malformed_envelope", "missing_tool"):
        error = record["agent"]["error"]
        assert error["code"] == "STEP_LIMIT" and "read_lidar" in error["message"]
        assert "get_belief_history" not in error["message"]
        history, = [c for c in record["agent"]["tool_calls"] if c["tool"] == "get_belief_history"]
        assert history["args"] == {"subject": "path_A", "predicate": "status"}
        assert history["result"]["ok"]
    if control == "malformed_envelope":
        assert any(not e.payload["canonical_envelope_valid"] for e in read_events(tmp_path / control / "trace.jsonl") if e.event_type == "teammate_boundary_return")
    if control == "provenance_guard":
        rejected = next(d for d in record["dispatch_outcomes"] if d["tool"] == "update_belief")
        assert rejected["rejected_before_dispatch"] and rejected["guard"]["refused"]


def test_contradictory_sensor_value_is_rejected_before_write(tmp_path):
    record = run_teammate_case("S01", tmp_path / "unsupported", "unsupported_update")
    assert record["expectation_met"] and record["evaluation"]["passed"]
    write = next(d for d in record["dispatch_outcomes"] if d["tool"] == "update_belief")
    assert write["rejected_before_dispatch"]
    assert write["agent_result"]["error"]["code"] == "INVALID_ARGUMENT"
    assert record["state_after"]["memory"] == record["state_before"]["memory"]


def test_recheck_cancels_a_move_toward_a_blocked_path(tmp_path):
    """P6 closed the old gap: a blocked path no longer lets the model move the robot."""
    record = run_teammate_case("S08", tmp_path / "movement", "movement_attempt")
    assert record["expectation_met"] and record["evaluation"]["passed"]
    movement = next(d for d in record["dispatch_outcomes"] if d["tool"] == "move_forward")
    assert movement["rejected_before_dispatch"] and not movement["dispatched"] and not movement["movement_observed"]
    assert movement["requested_arguments"]["distance_cm"] == 20
    assert movement["agent_result"]["error"]["code"] == "CONFLICT"
    assert "recheck before action" in movement["agent_result"]["error"]["message"]
    assert movement["guard"]["recheck"]["passed"] is False
    assert record["state_before"]["environment"]["robot"] == record["state_after"]["environment"]["robot"]
    assert record["agent"]["error"] is None and record["agent"]["answer_source"] == "llm"
    recheck = movement["guard"]["recheck"]
    assert f"front LiDAR now reads {recheck['reading_cm']} cm" in record["agent"]["answer"]
    assert "The robot did not move." in record["agent"]["answer"]


def test_canonical_mapping_preserves_validity_and_rejects_reference_fields(tmp_path):
    record = run_teammate_case("S01", tmp_path / "mapping")
    assert record["reference_aliases"]["path_a_map"] == "b_000001"
    raw = record["state_after"]["memory"]["nodes"][0]
    view = belief_view(raw)
    assert view["canonical"]["valid_to"] and view["canonical"]["status"] == "superseded"
    assert view["reference_view"]["value"] == raw["object"]
    with pytest.raises(ValidationError):
        Belief.model_validate(view["reference_view"])
    with pytest.raises(ValueError):
        canonical_timestamp("2026-10-06T09:00:00")


def test_s01_matches_the_demo_seed_and_two_write_chain(tmp_path):
    record = run_teammate_case("S01", tmp_path / "demo")
    old, = record["state_before"]["memory"]["nodes"]
    assert (old["object"], old["source"], old["confidence"]) == ("clear", "default_map", 1.0)
    calls = record["agent"]["tool_calls"]
    assert [c["tool"] for c in calls[:5]] == [
        "query_belief", "get_belief_history", "read_lidar", "downgrade_belief", "update_belief"
    ]
    assert calls[1]["args"] == {"subject": "path_A", "predicate": "status"}
    assert calls[1]["result"]["data"] == [old]
    assert calls[2]["result"]["data"]["value"] == 12
    initial, lowered, active = record["state_after"]["memory"]["nodes"]
    assert initial["belief_id"] == old["belief_id"] == lowered["supersedes"]
    assert initial["valid_to"] == lowered["valid_from"]
    assert lowered["confidence"] == 0.3 and lowered["status"] == "superseded"
    assert lowered["valid_to"] == active["valid_from"] and active["supersedes"] == lowered["belief_id"]
    assert (active["status"], active["source"], active["object"], active["confidence"]) == (
        "active", "lidar_front", "blocked", 0.98
    )
    assert all(token in record["agent"]["answer"] for token in (
        old["source"], active["source"], lowered["belief_id"], active["belief_id"]
    ))


def test_trace_verifier_requires_actual_automatic_read_boundaries(tmp_path):
    folder = tmp_path / "movement"
    record = run_teammate_case("S08", folder, "movement_attempt")
    events = read_events(folder / "trace.jsonl")
    move = next(d for d in record["dispatch_outcomes"] if d["tool"] == "move_forward")
    automatic = [e for e in events if e.event_type in {"teammate_boundary_call", "teammate_boundary_return"}
                 and (e.payload["call_id"], e.payload["tool"]) == (move["call_id"], "read_lidar")]
    assert len(automatic) == 2
    assert trace_consistent(record, events)
    assert not trace_consistent(record, [event for event in events if event not in automatic])
    altered = deepcopy(events)
    recheck_result = next(e for e in altered if e.event_type == "teammate_boundary_return"
                          and (e.payload["call_id"], e.payload["tool"]) == (move["call_id"], "read_lidar"))
    recheck_result.payload["raw"]["data"]["value"] = 100
    assert not trace_consistent(record, altered)


def test_artifact_tampering_breaks_delivery_consistency(tmp_path):
    folder = tmp_path / "trace"
    record = run_teammate_case("S01", folder)
    events = read_events(folder / "trace.jsonl")
    assert trace_consistent(record, events)
    corrupt = deepcopy(record)
    corrupt["agent"]["tool_calls"][0]["result"]["data"] = []
    assert not trace_consistent(corrupt, events)
    assert json.loads((folder / "run.json").read_text())["state_after"] == record["state_after"]
    assert verify_artifacts(tmp_path)["cases_verified"] == 1
    altered = deepcopy(record)
    altered["tool_sources"]["read_lidar"] = "tests.procedural.fakes.sensorimotor_fake"
    (folder / "run.json").write_text(json.dumps(altered))
    with pytest.raises(AssertionError):
        verify_artifacts(tmp_path)


def test_auto_fallbacks_are_rejected_even_if_use_real_is_requested():
    from declarative.belief_graph import BeliefMemory
    from sensorimotor import create_sensorimotor
    from scripts.tool_wiring import build_tool_registry
    memory = BeliefMemory()
    world = create_sensorimotor("scenario_a", seed=42)
    try:
        registry, sources = build_tool_registry(use_real=True, memory=memory, real_sensors=False)
        with pytest.raises(RuntimeError, match="fallback"):
            require_real_tools(registry, sources, memory, world)
    finally:
        memory.close()


def test_offline_guard_blocks_network_and_dotenv(monkeypatch):
    import dotenv
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-test-value")
    with offline_guard() as blocked:
        import os
        assert "GROQ_API_KEY" not in os.environ
        assert dotenv.load_dotenv() is False and dotenv.dotenv_values() == {}
        with pytest.raises(RuntimeError, match="network access prohibited"):
            socket.create_connection(("example.invalid", 443))
        assert blocked == ["network_attempt"]


def test_fresh_runs_are_isolated_and_outputs_never_overwrite(tmp_path):
    first = run_teammate_case("S08", tmp_path / "first", "movement_attempt")
    second = run_teammate_case("S08", tmp_path / "second")
    assert first["state_before"] == second["state_before"]
    assert first["state_after"]["environment"]["robot"] == second["state_after"]["environment"]["robot"]
    assert first["agent"]["tool_calls"][-1]["guard"]["recheck"]["passed"] is False  # only the first run tried to move
    with pytest.raises(FileExistsError):
        run_teammate_case("S08", tmp_path / "second")
