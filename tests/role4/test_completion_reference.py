"""Exercise the three restored synthetic cases and the dynamic fixture boundary."""

from copy import deepcopy

import pytest

from evaluation.role4.evaluator import evaluate
from evaluation.role4.final_reference import (
    CompletionDispatcher,
    CompletionPolicy,
    REFERENCE_FAULT_CHECKS,
    run_final_reference,
)
from evaluation.role4.integration.runner import _execute, load_scenario
from evaluation.role4.logger import read_events
from evaluation.role4.reference_layers.completion_reference import ChangingSensorReference, CompletionProceduralReference
from evaluation.role4.reference_layers.declarative_reference import DeclarativeReference


@pytest.mark.parametrize("scenario_id", ("S06", "S09", "S10"))
def test_completion_fixtures_pass_and_detect_their_injected_fault(tmp_path, scenario_id):
    valid = run_final_reference(scenario_id, output_dir=tmp_path)
    fault = run_final_reference(scenario_id, "fault", injected_fault=True, output_dir=tmp_path)
    assert valid.status == "PASS" and fault.status == "FAIL"
    assert valid.run.integration_metadata["fixture_origin"] == "synthetic_reference"
    assert REFERENCE_FAULT_CHECKS[scenario_id] <= {
        check["name"] for check in fault.run.result.checks if not check["passed"]
    }


def test_s10_requires_a_real_fixture_change_receipt(tmp_path):
    run = run_final_reference("S10", output_dir=tmp_path).run
    assert run.initial_environment_state["revision"] == 1
    assert run.integration_metadata["final_environment_state"]["revision"] == 2
    tampered = deepcopy(run)
    tampered.events = [
        event for event in tampered.events if event.payload.get("operation") != "advance_after_lidar"
    ]
    result = evaluate(load_scenario("S10"), tampered, CompletionPolicy(300))
    assert not result.passed
    assert any(c["name"] == "fixture_changed_after_first_read" and not c["passed"] for c in result.checks)


def test_s09_cannot_invent_provenance_in_both_claim_and_evidence(tmp_path):
    run = run_final_reference("S09", output_dir=tmp_path).run
    for event in run.events:
        if event.event_type == "tool_result" and event.payload.get("tool_name") == "query_memory":
            event.payload["evidence"][0]["data"]["source"] = "invented_source"
        if event.event_type == "agent_response":
            event.payload["claim_support"][0]["source"] = "invented_source"
    result = evaluate(load_scenario("S09"), run, CompletionPolicy(300))
    assert not result.passed
    assert any(c["name"] == "record_as_stored" and not c["passed"] for c in result.checks)


def test_s10_malformed_first_read_never_advances_fixture(tmp_path):
    scenario = load_scenario("S10")
    env = scenario.initial_environment_state
    sensors = ChangingSensorReference("S10", env, malformed_lidar=True)
    out = _execute(
        scenario, "malformed", DeclarativeReference("S10", scenario.initial_beliefs),
        CompletionProceduralReference("S10", env["fixture_time"], 300), sensors,
        output_dir=tmp_path, behavioral_policy=CompletionPolicy(300),
        metadata={"backend_type": "reference"}, dispatcher_type=CompletionDispatcher,
    )
    assert out.status == "CONTRACT ERROR"
    assert out.error["error_category"] == "malformed_payload"
    assert sensors.get_environment_revision() == 1
    assert not any(
        event.payload.get("operation") == "advance_after_lidar"
        for event in read_events(tmp_path / "S10_malformed_trace.jsonl")
    )
