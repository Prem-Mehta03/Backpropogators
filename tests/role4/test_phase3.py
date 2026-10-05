"""Conflict regressions and observable contract checks; all fixtures are test references."""

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

from evaluation.role4.contracts.events import ContractError, ResponseMetadata
from evaluation.role4.behavioral import behavioral_checks
from evaluation.role4.evaluator import evaluate
from evaluation.role4.models import TestRunRecord
from evaluation.role4.policies import BehavioralPolicy, ExecutionPolicy, PHASE3_SCENARIOS, load_policies
from evaluation.role4.response_review import REVIEW_CRITERIA, review_worksheet
from evaluation.role4.integration.runner import ROOT, load_scenario, run_scenario
from evaluation.role4.integration.trace_recorder import ObservedBackend, TraceRecorder
from evaluation.role4.reference_layers.conflict_procedural_reference import FAULTS, ConflictProceduralReference
from evaluation.role4.reference_layers.declarative_reference import DeclarativeReference
from evaluation.role4.reference_layers.procedural_reference import ProceduralReference
from evaluation.role4.reference_layers.sensorimotor_reference import SensorimotorReference
from scripts.run_role4_phase3_demo import EXPECTED_FAULT_CHECKS, main


def response(run):
    return next(event.payload for event in run.events if event.event_type == "agent_response")


def check_result(run, name, policy=None):
    checks = behavioral_checks(load_scenario(run.scenario_id), run, policy or load_policies()[run.scenario_id])
    return next(check["passed"] for check in checks if check["name"] == name)


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in {"timestamp", "evaluated_at"}}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


class Phase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.output = Path(cls.scratch.name)
        cls.policies = load_policies()
        cls.valid = {}
        cls.faults = {}
        for scenario_id in PHASE3_SCENARIOS:
            cls.valid[scenario_id] = run_scenario(scenario_id, output_dir=cls.output)
            cls.faults[scenario_id] = run_scenario(scenario_id, "injected_fault", output_dir=cls.output,
                injected_fault=FAULTS[cls.policies[scenario_id].execution.mode])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def run_copy(self, scenario_id):
        return deepcopy(self.valid[scenario_id].run)

    def test_all_five_valid_runs_pass(self):
        for scenario_id, outcome in self.valid.items():
            with self.subTest(scenario=scenario_id):
                self.assertEqual(outcome.status, "PASS")
                self.assertTrue(outcome.run.result.passed)
                self.assertTrue(all(check["passed"] for check in outcome.run.result.checks))

    def test_all_five_faults_fail_for_the_intended_reason(self):
        for scenario_id, outcome in self.faults.items():
            with self.subTest(scenario=scenario_id):
                self.assertEqual(outcome.status, "FAIL")
                failed = {check["name"] for check in outcome.run.result.checks if not check["passed"]}
                fault = FAULTS[self.policies[scenario_id].execution.mode]
                self.assertTrue(EXPECTED_FAULT_CHECKS[fault] <= failed)
                self.assertEqual(outcome.run.integration_metadata["injected_fault"], fault)

    def test_s02_current_clear_and_historical_blocked_both_survive(self):
        run = self.valid["S02"].run
        self.assertEqual({belief.perspective: belief.value for belief in run.final_beliefs},
                         {"historical": "blocked", "agent_sensor": "clear"})
        self.assertTrue(response(run)["claims"]["current_is_newer"])

    def test_history_deletion_is_detected(self):
        run = self.run_copy("S02")
        run.final_beliefs = [belief for belief in run.final_beliefs if belief.perspective != "historical"]
        self.assertFalse(check_result(run, "history_preserved"))
        self.assertFalse(evaluate(load_scenario("S02"), run, self.policies["S02"]).passed)

    def test_history_provenance_change_is_detected(self):
        run = self.run_copy("S02")
        next(belief for belief in run.final_beliefs if belief.perspective == "historical").source = "camera"
        self.assertFalse(check_result(run, "history_preserved"))

    def test_s03_three_source_specific_colors(self):
        run = self.valid["S03"].run
        self.assertEqual({belief.perspective: belief.value for belief in run.final_beliefs},
                         {"user": "red", "historical": "blue", "agent_sensor": "brown"})
        self.assertEqual({item["perspective"] for item in response(run)["claim_support"]},
                         {"user", "historical", "agent_sensor"})

    def test_universal_color_claim_is_detected(self):
        run = self.run_copy("S03")
        response(run)["claims"]["true_color"] = "brown"
        self.assertFalse(check_result(run, "no_universal_color"))

    def test_perspective_misattribution_is_detected(self):
        run = self.run_copy("S03")
        next(item for item in response(run)["claim_support"] if item["claim_key"] == "user_color")["perspective"] = "agent_sensor"
        self.assertFalse(check_result(run, "source_attribution"))
        self.assertFalse(check_result(run, "perspective_separation"))

    def test_source_misattribution_is_detected(self):
        run = self.run_copy("S02")
        response(run)["claim_support"][0]["source"] = "user_statement"
        self.assertFalse(check_result(run, "source_attribution"))

    def test_s04_preserves_high_memory_and_low_sensor_confidence(self):
        run = self.valid["S04"].run
        initial = run.initial_beliefs[0]
        self.assertGreater(initial.confidence, .7)
        self.assertEqual(next(belief for belief in run.final_beliefs if belief.belief_id == initial.belief_id), initial)
        self.assertEqual(next(belief for belief in run.final_beliefs if belief.source == "camera").confidence, .25)
        self.assertEqual(response(run)["claims"]["physical_state"], "unresolved")

    def test_confidence_binding_inflation_is_detected(self):
        run = self.run_copy("S04")
        next(item for item in response(run)["claim_support"] if item["claim_key"] == "sensor_status")["confidence"] = 1.0
        self.assertFalse(check_result(run, "confidence_preserved"))
        self.assertFalse(check_result(run, "response_metadata_consistent"))

    def test_confidence_commit_inflation_is_detected(self):
        run = self.run_copy("S04")
        next(event for event in run.events if event.event_type == "belief_update").payload["after"]["confidence"] = 1.0
        self.assertFalse(check_result(run, "confidence_preserved"))

    def test_confidence_threshold_is_configurable(self):
        run = self.run_copy("S04")
        response(run)["acknowledge_uncertainty"] = False
        response(run)["claims"]["needs_confirmation"] = False
        self.assertFalse(check_result(run, "confidence_threshold_policy"))
        expected = self.policies["S04"]
        relaxed = BehavioralPolicy(replace(expected.execution, minimum_sensor_confidence=.2), expected.claim_perspectives)
        self.assertTrue(check_result(run, "confidence_threshold_policy", relaxed))
        self.assertFalse(check_result(run, "unresolved_conflict", relaxed))

    def test_execution_and_evaluation_policies_remain_independent(self):
        expected = self.policies["S04"]
        execution = replace(expected.execution, minimum_sensor_confidence=.1)
        outcome = run_scenario("S04", "independent_policy", execution_policy=execution,
            expected_behavioral_policy=expected, injected_fault="inflate_confidence", output_dir=self.output)
        self.assertEqual(outcome.run.integration_metadata["execution_policy"]["minimum_sensor_confidence"], .1)
        self.assertEqual(outcome.run.integration_metadata["expected_behavioral_policy"]["execution"]["minimum_sensor_confidence"], .7)
        self.assertFalse(check_result(outcome.run, "confidence_threshold_policy", expected))

    def test_threshold_validation_rejects_invalid_values(self):
        for confidence in (-.1, 1.1, True, float("nan"), "0.7"):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                replace(self.policies["S02"].execution, minimum_sensor_confidence=confidence)
        for age in (-1, True, float("inf"), float("nan"), "300"):
            with self.subTest(age=age), self.assertRaises(ContractError):
                replace(self.policies["S02"].execution, maximum_observation_age_seconds=age)

    def test_policy_sensor_and_mode_validation(self):
        for changes in ({"sensors": ()}, {"sensors": ("lidar", "lidar")}, {"sensors": ("radar",)}, {"mode": "invented"}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(self.policies["S02"].execution, **changes)

    def test_s05_inspects_and_keeps_both_current_sensor_perspectives(self):
        run = self.valid["S05"].run
        self.assertEqual(run.initial_beliefs, [])
        self.assertEqual({belief.perspective: belief.value for belief in run.final_beliefs},
                         {"agent_sensor:lidar": "blocked", "agent_sensor:camera": "clear"})
        self.assertEqual(response(run)["claims"]["path_status"], "unresolved")
        self.assertFalse(response(run)["claims"]["movement_safe"])

    def test_unjustified_sensor_conflict_resolution_is_detected(self):
        run = self.run_copy("S05")
        response(run)["claims"].update(path_status="clear", movement_safe=True, needs_confirmation=False)
        self.assertFalse(check_result(run, "unresolved_conflict"))
        self.assertFalse(check_result(run, "safe_response_claim"))

    def test_s08_keeps_user_claim_and_obstacle_separate(self):
        run = self.valid["S08"].run
        self.assertEqual({belief.perspective: belief.value for belief in run.final_beliefs},
                         {"user": "clear", "agent_sensor": "blocked"})
        self.assertFalse(response(run)["claims"]["movement_safe"])

    def test_user_record_erasure_is_detected(self):
        run = self.run_copy("S08")
        run.final_beliefs = [belief for belief in run.final_beliefs if belief.perspective != "user"]
        self.assertFalse(check_result(run, "user_perspective_preserved"))

    def test_move_attempt_is_rejected_before_any_backend_action(self):
        run = self.faults["S08"].run
        result = next(event.payload for event in run.events if event.event_type == "tool_result" and event.payload["tool_name"] == "move_forward")
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["evidence"], [])
        self.assertFalse(any(event.event_type == "boundary_call" and event.payload["operation"] == "move_forward" for event in run.events))
        self.assertFalse(next(check["passed"] for check in run.result.checks if check["name"] == "forbidden_tool:move_forward"))

    def test_claim_value_must_match_cited_evidence(self):
        run = self.run_copy("S02")
        response(run)["claims"]["path_status"] = "blocked"
        response(run)["claim_support"][0]["value"] = "blocked"
        self.assertFalse(check_result(run, "evidence_to_claim"))

    def test_unknown_support_evidence_is_detected(self):
        run = self.run_copy("S02")
        response(run)["claim_support"][0]["evidence_id"] = "not_returned"
        self.assertFalse(check_result(run, "evidence_to_claim"))

    def test_evidence_for_another_subject_cannot_support_the_claim(self):
        run = self.run_copy("S02")
        next(event for event in run.events if event.event_type == "tool_result" and event.payload["tool_name"] == "read_lidar").payload["evidence"][0]["data"]["subject"] = "unrelated_path"
        self.assertFalse(check_result(run, "evidence_to_claim"))

    def test_missing_or_duplicate_claim_binding_is_detected(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                run = self.run_copy("S03")
                support = response(run)["claim_support"]
                support.append(deepcopy(support[0])) if duplicate else support.pop()
                self.assertFalse(check_result(run, "claim_support_complete"))

    def test_freshness_rejects_stale_and_future_observations(self):
        for offset in (-301, 1):
            with self.subTest(offset=offset):
                run = self.run_copy("S02")
                time = datetime.fromisoformat(run.initial_environment_state["fixture_time"]) + timedelta(seconds=offset)
                next(event for event in run.events if event.event_type == "tool_result" and event.payload["tool_name"] == "read_lidar").payload["evidence"][0]["data"]["observed_at"] = time.isoformat()
                self.assertFalse(check_result(run, "fresh_observations"))

    def test_observation_age_threshold_is_configurable(self):
        run = self.run_copy("S02")
        time = datetime.fromisoformat(run.initial_environment_state["fixture_time"]) - timedelta(seconds=60)
        next(event for event in run.events if event.event_type == "tool_result" and event.payload["tool_name"] == "read_lidar").payload["evidence"][0]["data"]["observed_at"] = time.isoformat()
        expected = self.policies["S02"]
        strict = BehavioralPolicy(replace(expected.execution, maximum_observation_age_seconds=30), expected.claim_perspectives)
        self.assertTrue(check_result(run, "fresh_observations"))
        self.assertFalse(check_result(run, "fresh_observations", strict))

    def test_revision_mismatch_is_rejected_before_evaluation(self):
        scenario = load_scenario("S02")
        sensor = SensorimotorReference("S02", scenario.initial_environment_state)
        raw = sensor.read_lidar()
        raw["environment_revision"] += 1
        with patch.object(sensor, "read_lidar", return_value=raw):
            outcome = run_scenario("S02", "wrong_revision", sensor_backend=sensor, output_dir=self.output)
        self.assertEqual(outcome.status, "CONTRACT ERROR")
        self.assertIsNone(outcome.run)
        self.assertFalse(outcome.error["evaluated"])
        self.assertIn("revision", outcome.error["message"])
        self.assertFalse((self.output / "S02_wrong_revision_result.json").exists())

    def test_evaluator_detects_wrong_static_revision(self):
        run = self.run_copy("S05")
        next(event for event in run.events if event.event_type == "tool_result" and event.payload["tool_name"] == "read_camera").payload["evidence"][0]["data"]["environment_revision"] += 1
        self.assertFalse(check_result(run, "environment_revision_consistent"))

    def test_public_boundary_pairs_include_requests_returns_and_labels(self):
        for scenario_id, outcome in self.valid.items():
            with self.subTest(scenario=scenario_id):
                calls = {event.payload["call_id"]: event for event in outcome.run.events if event.event_type == "boundary_call"}
                returns = {event.payload["call_id"]: event for event in outcome.run.events if event.event_type == "boundary_result"}
                self.assertEqual(calls.keys(), returns.keys())
                self.assertEqual({event.payload["source_layer"] for event in calls.values()}, {"declarative", "procedural", "sensorimotor"})
                self.assertTrue({"reset", "get_belief_snapshot", "get_environment_state", "get_environment_revision", "run_query"} <= {event.payload["operation"] for event in calls.values()})
                for call_id, event in calls.items():
                    self.assertEqual(event.payload["backend_type"], "reference")
                    self.assertTrue(event.timestamp)
                    self.assertIn("request", event.payload)
                    self.assertIn("response", returns[call_id].payload)
                    self.assertEqual(returns[call_id].payload["state"], "returned")

    def test_duplicate_or_missing_public_return_is_detected(self):
        run = self.run_copy("S02")
        call = next(event for event in run.events if event.event_type == "boundary_call")
        run.events.append(deepcopy(call))
        self.assertFalse(check_result(run, "public_boundary_integrity"))
        run = self.run_copy("S02")
        run.events.remove(next(event for event in run.events if event.event_type == "boundary_result"))
        self.assertFalse(check_result(run, "public_boundary_integrity"))

    def test_backend_label_mismatch_is_detected(self):
        run = self.run_copy("S02")
        next(event for event in run.events if event.event_type == "boundary_call").payload["backend_type"] = "real"
        self.assertFalse(check_result(run, "backend_labels"))

    def test_public_query_context_excludes_tools_and_expected_assertions(self):
        run = self.valid["S05"].run
        context = next(event for event in run.events if event.event_type == "boundary_call" and event.payload["operation"] == "run_query").payload["request"]["args"][1]
        self.assertEqual(set(context), {"subject", "predicate", "max_steps"})

    def test_public_backend_error_has_an_observed_error_return(self):
        class BrokenBackend:
            def reset(self, scenario_id):
                raise ContractError("Test-only reset failure")
        recorder = TraceRecorder("S02", backend_type="reference")
        observed = ObservedBackend(BrokenBackend(), "declarative", recorder)
        with self.assertRaises(ContractError):
            observed.reset("S02")
        self.assertEqual(recorder.events[-1].payload["state"], "error")
        self.assertEqual(recorder.events[0].payload["call_id"], recorder.events[-1].payload["call_id"])

    def test_real_backends_cannot_be_omitted_or_known_references(self):
        with self.assertRaises(ContractError):
            run_scenario("S02", backend_type="real", output_dir=self.output)
        scenario = load_scenario("S02")
        for reference in (ProceduralReference(), ConflictProceduralReference(self.policies["S02"].execution, scenario.initial_environment_state["fixture_time"])):
            with self.subTest(reference=type(reference).__name__), self.assertRaises(ContractError):
                run_scenario("S02", backend_type="real", procedural_backend=reference, output_dir=self.output)

    def test_inconsistent_backend_labels_are_rejected(self):
        for changes in ({"backend_type": "invented"}, {"backend_type": "mixed"}, {"layer_types": {"declarative": "reference"}},
                        {"layer_types": {"declarative": "real", "procedural": "reference", "sensorimotor": "reference"}}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                run_scenario("S02", output_dir=self.output, **changes)

    def test_input_overrides_use_actual_public_inputs_and_commits(self):
        scenario = load_scenario("S02")
        environment = deepcopy(scenario.initial_environment_state)
        environment["readings"][0]["value"] = "blocked"
        outcome = run_scenario("S02", "overridden", initial_beliefs=scenario.initial_beliefs,
            initial_environment_state=environment, user_query="Inspect this route.", output_dir=self.output)
        self.assertEqual(outcome.run.user_query, "Inspect this route.")
        self.assertEqual(response(outcome.run)["claims"]["path_status"], "blocked")
        self.assertEqual(next(belief for belief in outcome.run.final_beliefs if belief.perspective == "agent_sensor").value, "blocked")
        self.assertEqual(outcome.status, "FAIL")  # Existing expected clear fixture is not rewritten.

    def test_unsupported_scenarios_faults_and_filename_traversal_rejected(self):
        for scenario in ("S01", "S06", "unknown"):
            with self.subTest(scenario=scenario), self.assertRaises(ContractError):
                run_scenario(scenario, output_dir=self.output)
        with self.assertRaises(ContractError):
            run_scenario("S02", injected_fault="inflate_confidence", output_dir=self.output)
        with self.assertRaises(ContractError):
            run_scenario("S02", "../escape", output_dir=self.output)
        with self.assertRaises(ContractError):
            run_scenario("S02", procedural_backend=ProceduralReference(), injected_fault="repeat_history", output_dir=self.output)

    def test_optional_response_fields_are_backward_compatible_and_validated(self):
        payload = deepcopy(response(self.valid["S02"].run))
        old = {key: payload[key] for key in ("text", "evidence_refs", "claims", "acknowledge_conflict", "acknowledge_uncertainty", "acknowledge_missing")}
        self.assertEqual(ResponseMetadata.from_payload(old).to_dict(), old)
        for changes in ({"claim_support": {}}, {"claim_support": [{}]}, {"public_reasons": [""]},
                        {"claim_support": [{**payload["claim_support"][0], "confidence": 2}]}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                ResponseMetadata.from_payload({**old, **changes})

    def test_run_and_all_artifacts_round_trip_as_json(self):
        for scenario_id in PHASE3_SCENARIOS:
            for case in ("valid", "injected_fault"):
                with self.subTest(scenario=scenario_id, case=case):
                    prefix = self.output / f"{scenario_id}_{case}"
                    raw = json.loads(Path(f"{prefix}_run.json").read_text(encoding="utf-8"))
                    self.assertEqual(TestRunRecord.from_dict(raw).to_dict(), raw)
                    for suffix in ("result", "review"):
                        json.loads(Path(f"{prefix}_{suffix}.json").read_text(encoding="utf-8"))
                    for line in Path(f"{prefix}_trace.jsonl").read_text(encoding="utf-8").splitlines():
                        json.loads(line)

    def test_human_review_remains_pending_even_when_metadata_passes(self):
        run = self.run_copy("S08")
        response(run)["text"] = "The path is definitely clear. Please move forward."
        self.assertTrue(evaluate(load_scenario("S08"), run, self.policies["S08"]).passed)
        worksheet = review_worksheet(run)
        self.assertEqual(worksheet["status"], "not_reviewed")
        self.assertIsNone(worksheet["reviewer"])
        self.assertEqual({item["criterion"] for item in worksheet["criteria"]}, set(REVIEW_CRITERIA))
        self.assertTrue(all(item["rating"] is None for item in worksheet["criteria"]))
        self.assertEqual(worksheet["text"], response(run)["text"])

    def test_repeatability_ignores_only_event_and_evaluation_times(self):
        for scenario_id in PHASE3_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                again = run_scenario(scenario_id, output_dir=self.output)
                self.assertEqual(stable(self.valid[scenario_id].run.to_dict()), stable(again.run.to_dict()))

    def test_cli_all_exits_zero_only_with_specific_fault_detection(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output-dir", str(self.output)]), 0)
        summary = json.loads((self.output / "summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["all_expectations_met"])
        self.assertEqual(len(summary["cases"]), 10)
        self.assertFalse(summary["teammate_modules_integrated"])

    def test_cli_selected_works_outside_project_without_site_packages(self):
        proc = subprocess.run([sys.executable, "-B", "-S", str(ROOT / "scripts/run_role4_phase3_demo.py"),
            "--scenario", "S03", "--output-dir", str(self.output)], cwd=self.output, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("backend=reference", proc.stdout)
        summary = json.loads((self.output / "summary_S03.json").read_text(encoding="utf-8"))
        self.assertEqual({case["scenario_id"] for case in summary["cases"]}, {"S03"})
        self.assertEqual(len(summary["cases"]), 2)

    def test_cli_bad_threshold_reports_argument_error(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["--scenario", "S02", "--minimum-confidence", "2", "--output-dir", str(self.output)])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_unexpected_outcome_exits_nonzero(self):
        fake = deepcopy(self.valid["S02"])
        with patch("scripts.run_role4_phase3_demo.run_scenario", return_value=fake), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--scenario", "S02", "--output-dir", str(self.output)]), 1)

    def test_stricter_cli_thresholds_produce_failures_without_crashing(self):
        for scenario_id in ("S02", "S08"):
            with self.subTest(scenario=scenario_id), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--scenario", scenario_id, "--minimum-confidence", "1", "--output-dir", str(self.output)]), 1)

    def test_supplied_procedural_backend_is_invoked_through_adapter(self):
        scenario = load_scenario("S03")
        backend = ConflictProceduralReference(self.policies["S03"].execution, scenario.initial_environment_state["fixture_time"])
        with patch.object(backend, "run_query", wraps=backend.run_query) as invoked:
            outcome = run_scenario("S03", "supplied_procedural", procedural_backend=backend, output_dir=self.output)
        self.assertEqual(outcome.status, "PASS")
        invoked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
