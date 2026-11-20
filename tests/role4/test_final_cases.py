"""Verify canonical final fixtures and the evidence for their known defects."""

import json

import pytest

from evaluation.role4.integration.final_cases import (
    FINAL_SCENARIOS,
    S05_FIXTURE_SOURCE,
    S05_REAL_SOURCE,
    run_final_case,
    verify_final_case_artifacts,
)
from evaluation.role4.logger import read_events


@pytest.mark.parametrize("scenario", FINAL_SCENARIOS)
def test_final_case_outcomes_and_evidence(scenario, tmp_path):
    output = tmp_path / scenario
    result = run_final_case(scenario, output)
    agent = result["agent"]

    assert result["expectation_met"]
    assert result["labels"]["human_semantic_review"] == "pending"
    assert result["labels"]["fixture_origin"] == "role4_synthetic_scenario"
    assert verify_final_case_artifacts(output) == {
        "cases_verified": 1,
        "json_jsonl_files_parsed": 4,
    }
    states = result["state_after"]["memory"]["nodes"]

    if scenario == "S09":
        assert result["evaluation"]["failure_reasons"] == ["agent_delivered_scripted_answer"]
        assert result["labels"]["per_layer_backend"]["sensorimotor"] == "not_exercised"
        assert result["failure_layers"] == {"agent_delivered_scripted_answer": "procedural"}
        assert agent["error"]["code"] == "STEP_LIMIT"
        query, battery = agent["tool_calls"]
        source = query["result"]["data"][0]
        assert source["source"] is None and source["confidence"] == 0.5
        assert states == [source]
        assert battery["tool"] == "read_battery"
        assert battery["result"]["error"]["code"] == "INVALID_ARGUMENT"
        assert result["dispatch_outcomes"][-1]["rejected_before_dispatch"]
    else:
        assert result["evaluation"]["passed"] and agent["answer"]
        assert agent["error"] is None

    if scenario == "S04":
        assert {(b["object"], b["confidence"], b["status"]) for b in states} == {
            ("clear", 0.96, "active"),
            ("blocked", 0.25, "disputed"),
        }
    if scenario == "S05":
        lidar = [d for d in result["dispatch_outcomes"] if d["tool"] == "read_lidar"]
        assert [(r["source"], r["agent_result"]["data"]["status"]) for r in lidar] == [
            (S05_REAL_SOURCE, "blocked"),
            (S05_FIXTURE_SOURCE, "clear"),
        ]
        assert result["labels"]["per_layer_backend"]["sensorimotor"] == "mixed"
        assert not result["labels"]["all_real_tools"]
    if scenario == "S06":
        old, current = states
        assert old["valid_to"] == current["timestamp"]
        assert current["supersedes"] == old["belief_id"]
        assert old["status"] == "superseded"


def test_s10_records_change_between_observations_and_exposes_stale_action(tmp_path):
    valid_dir = tmp_path / "valid"
    valid = run_final_case("S10", valid_dir)
    fault_dir = tmp_path / "stale_action"
    fault = run_final_case("S10", fault_dir, control="stale_action")
    valid_events = read_events(valid_dir / "trace.jsonl")
    timeline = [
        event.payload["raw"]["data"]["status"]
        if event.event_type == "teammate_boundary_return"
        else "world_change"
        for event in valid_events
        if event.event_type == "role4_world_change"
        or (event.event_type == "teammate_boundary_return"
            and event.payload["tool"] == "read_lidar")
    ]

    assert timeline == ["clear", "world_change", "blocked"]
    assert valid["state_before"] == fault["state_before"]
    assert valid["state_after"]["environment"]["robot"]["x"] == 0
    assert fault["evaluation"]["failure_reasons"] == [
        "rechecked_after_world_change",
        "current_sensor_belief_retained",
        "no_motion_on_changed_route",
    ]
    action = next(d for d in fault["dispatch_outcomes"] if d["tool"] == "move_forward")
    assert action["requested_arguments"] == {"distance_cm": 20}
    assert action["dispatched"] and action["movement_observed"]
    assert fault["state_after"]["environment"]["robot"]["x"] == 11
    assert verify_final_case_artifacts(fault_dir)["cases_verified"] == 1


def test_final_verifier_detects_a_changed_result_log(tmp_path):
    output = tmp_path / "tampered"
    run_final_case("S05", output)
    log = next((output / "official").glob("*.json"))
    official = json.loads(log.read_text(encoding="utf-8"))
    official["answer"] = "I trust that path_A is clear."
    log.write_text(json.dumps(official), encoding="utf-8")

    with pytest.raises(ValueError, match="Inconsistent final case artifacts"):
        verify_final_case_artifacts(output)
