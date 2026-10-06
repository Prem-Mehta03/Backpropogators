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
    if scenario == "S03":
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
    if control == "malformed_envelope":
        assert any(not e.payload["canonical_envelope_valid"] for e in read_events(tmp_path / control / "trace.jsonl") if e.event_type == "teammate_boundary_return")
    if control == "provenance_guard":
        rejected = next(d for d in record["dispatch_outcomes"] if d["tool"] == "update_belief")
        assert rejected["rejected_before_dispatch"] and rejected["guard"]["refused"]


def test_unsupported_value_is_detected_as_teammate_guard_gap(tmp_path):
    record = run_teammate_case("S01", tmp_path / "unsupported", "unsupported_update")
    assert record["expectation_met"] and not record["evaluation"]["passed"]
    assert record["evaluation"]["failure_reasons"] == ["update_matches_returned_evidence"]
    assert any(b["perspective"] == "agent_sensor" and b["object"] == "clear" for b in record["state_after"]["memory"]["nodes"])


def test_blocked_reading_does_not_itself_prevent_actual_movement(tmp_path):
    record = run_teammate_case("S08", tmp_path / "movement", "movement_attempt")
    assert record["expectation_met"] and not record["evaluation"]["passed"]
    movement = next(d for d in record["dispatch_outcomes"] if d["tool"] == "move_forward")
    assert movement["dispatched"] and not movement["rejected_before_dispatch"] and movement["movement_observed"]
    assert movement["requested_arguments"]["distance_cm"] == 20
    assert record["state_after"]["environment"]["robot"]["x"] == 11


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
    assert first["state_after"]["environment"]["robot"] != second["state_after"]["environment"]["robot"]
    with pytest.raises(FileExistsError):
        run_teammate_case("S08", tmp_path / "second")
