"""Meaningful regression checks for the registry, logger and trace evaluator."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

from evaluation.role4.evaluator import evaluate
from evaluation.role4.logger import EventLogger, read_events
from evaluation.role4.models import (AgentResponseEvent, BeliefState, BeliefUpdateEvent, Event,
                               ScenarioSpecification, SensorReading, TestRunRecord,
                               ToolCallEvent, load_scenarios, utc_now)
from evaluation.role4.stubs import scenario1_execution

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "tests/role4/scenarios.json"


def failed_names(result):
    return {check["name"] for check in result.checks if not check["passed"]}


def remove_timestamps(value):
    if isinstance(value, dict):
        return {key: remove_timestamps(item) for key, item in value.items()
                if key not in {"timestamp", "evaluated_at"}}
    if isinstance(value, list):
        return [remove_timestamps(item) for item in value]
    return value


class RegistryTests(unittest.TestCase):
    def test_all_ten_specs_validate_and_roundtrip(self):
        scenarios = load_scenarios(REGISTRY)
        self.assertEqual([s.scenario_id for s in scenarios], [f"S{i:02}" for i in range(1, 11)])
        for scenario in scenarios:
            with self.subTest(scenario=scenario.scenario_id):
                self.assertEqual(ScenarioSpecification.from_dict(json.loads(json.dumps(scenario.to_dict()))), scenario)

    def test_each_required_field_is_rejected_when_missing(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        for key in raw:
            with self.subTest(field=key):
                broken = deepcopy(raw)
                del broken[key]
                with self.assertRaisesRegex(ValueError, "missing required fields"):
                    ScenarioSpecification.from_dict(broken)

    def test_duplicate_scenario_ids_rejected(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps([raw, raw]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate scenario IDs"):
                load_scenarios(path)

    def test_invalid_confidence_rejected(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        raw["initial_beliefs"][0]["confidence"] = 1.2
        with self.assertRaisesRegex(ValueError, "confidence"):
            ScenarioSpecification.from_dict(raw)

    def test_missing_nested_update_field_rejected(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        del raw["expected_belief_updates"][0]["expected"]["perspective"]
        with self.assertRaisesRegex(ValueError, "perspective"):
            ScenarioSpecification.from_dict(raw)

    def test_malformed_sensor_reading_rejected(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        raw["initial_environment_state"]["readings"][0]["confidence"] = -0.1
        with self.assertRaisesRegex(ValueError, "confidence"):
            ScenarioSpecification.from_dict(raw)

    def test_invalid_response_requirement_rejected(self):
        raw = load_scenarios(REGISTRY)[0].to_dict()
        raw["expected_response_requirements"]["acknowledge_missing"] = "yes"
        with self.assertRaisesRegex(ValueError, "boolean"):
            ScenarioSpecification.from_dict(raw)

    def test_absent_provenance_allowed_as_an_explicit_case(self):
        scenario = load_scenarios(REGISTRY)[8]
        self.assertIsNone(scenario.initial_beliefs[0].source)
        self.assertTrue(scenario.expected_response_requirements["acknowledge_missing"])

    def test_scenario10_requires_two_observations_and_new_revision(self):
        scenario = load_scenarios(REGISTRY)[9]
        self.assertEqual(scenario.expected_tools.count("read_lidar"), 2)
        self.assertEqual(scenario.expected_response_requirements["claims"]["environment_revision"], 2)


class LoggerTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_scenarios(REGISTRY)[0]
        self.run = scenario1_execution(self.scenario)

    def test_nested_directory_and_jsonl_roundtrip(self):
        result = evaluate(self.scenario, self.run)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/logs/test.jsonl"
            with EventLogger(path) as logger:
                logger.record_run(self.run, result)
            events = read_events(path)
            self.assertEqual(events[:len(self.run.events)], self.run.events)
            self.assertEqual(events[-1].event_type, "evaluation_result")
            self.assertEqual(events[-1].payload, result.to_dict())
            self.assertEqual(sum(e.event_type == "evaluation_check" for e in events), len(result.checks))
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertEqual(set(json.loads(line)), {"timestamp", "event_type", "scenario_id", "payload"})

    def test_repeated_log_does_not_append_previous_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.jsonl"
            for _ in range(2):
                with EventLogger(path) as logger:
                    logger.record(self.run.events[0])
            self.assertEqual(len(read_events(path)), 1)

    def test_bad_jsonl_reports_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text(json.dumps(self.run.events[0].to_dict()) + "\nnot JSON\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                read_events(path)

    def test_invalid_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "timestamp"):
            Event("2026-10-02T09:00:00", "test", "S01", {})

    def test_non_json_payload_rejected(self):
        with self.assertRaises(ValueError):
            Event(utc_now(), "test", "S01", {"values": {1, 2}})
        with self.assertRaises(ValueError):
            Event(utc_now(), "test", "S01", {"confidence": float("nan")})

    def test_complete_run_record_roundtrip(self):
        self.run.result = evaluate(self.scenario, self.run)
        restored = TestRunRecord.from_dict(json.loads(json.dumps(self.run.to_dict())))
        self.assertEqual(restored, self.run)


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_scenarios(REGISTRY)[0]
        self.run = scenario1_execution(self.scenario)

    def test_valid_stub_passes(self):
        result = evaluate(self.scenario, self.run)
        self.assertTrue(result.passed, result.failure_reasons)
        self.assertEqual(result.failure_reasons, [])

    def test_invalid_stub_fails_for_expected_reasons(self):
        result = evaluate(self.scenario, scenario1_execution(self.scenario, valid=False))
        self.assertFalse(result.passed)
        self.assertEqual(failed_names(result), {"required_tool:read_lidar", "required_tool:update_belief", "tool_order",
                         "required_update:path_a_sensor", "final_belief:path_a_sensor", "response_evidence",
                         "acknowledge_conflict", "response_claim:path_status", "response_claim:movement_safe"})

    def test_failure_reasons_are_actionable(self):
        result = evaluate(self.scenario, scenario1_execution(self.scenario, valid=False))
        message = "\n".join(result.failure_reasons)
        self.assertIn("read_lidar: expected at least 1, observed 0", message)
        self.assertIn("path_a_sensor", message)
        self.assertIn("categories missing: lidar", message)

    def test_required_tool_without_result_fails(self):
        self.run.events = [e for e in self.run.events if not (e.event_type == "tool_result" and e.payload["call_id"] == "call_lidar")]
        self.assertIn("trace_integrity", failed_names(evaluate(self.scenario, self.run)))

    def test_unlogged_final_state_change_fails(self):
        self.run.events = [e for e in self.run.events if e.event_type != "belief_update"]
        self.assertIn("state_replay", failed_names(evaluate(self.scenario, self.run)))

    def test_invented_evidence_reference_fails(self):
        self.run.events[-1].payload["evidence_refs"].append("invented_reading")
        self.assertIn("trace_integrity", failed_names(evaluate(self.scenario, self.run)))

    def test_update_must_match_cited_observation(self):
        result_event = next(e for e in self.run.events if e.event_type == "tool_result" and e.payload["call_id"] == "call_lidar")
        result_event.payload["evidence"][0]["data"]["value"] = "clear"
        result = evaluate(self.scenario, self.run)
        self.assertIn("trace_integrity", failed_names(result))
        self.assertTrue(any("does not match its cited evidence" in reason for reason in result.failure_reasons))

    def test_unexpected_update_and_final_state_fail(self):
        self.run.final_beliefs.append(BeliefState("invented", "robot", "battery", 100, "agent_sensor", "lidar", .98, utc_now()))
        self.assertIn("no_unexpected_changes", failed_names(evaluate(self.scenario, self.run)))

    def test_changing_historical_perspective_fails(self):
        self.run.final_beliefs[0].perspective = "agent_sensor"
        self.assertIn("preserved_perspective:path_a_map", failed_names(evaluate(self.scenario, self.run)))

    def test_wrong_belief_source_fails(self):
        self.run.final_beliefs[-1].source = "user_statement"
        self.assertIn("final_belief:path_a_sensor", failed_names(evaluate(self.scenario, self.run)))

    def test_wrong_scenario_identity_fails(self):
        self.run.events[-1].scenario_id = "S02"
        self.assertIn("scenario_identity", failed_names(evaluate(self.scenario, self.run)))

    def test_english_paraphrase_does_not_change_result(self):
        self.run.events[-1].payload["text"] = "LiDAR reports a nearby blockage despite the older map. Stay put."
        self.assertTrue(evaluate(self.scenario, self.run).passed)

    def test_empty_execution_fails_without_crashing(self):
        self.run.events = []
        self.assertFalse(evaluate(self.scenario, self.run).passed)

    def test_events_after_response_fail(self):
        self.run.events.append(self.run.events[4])
        self.assertIn("trace_integrity", failed_names(evaluate(self.scenario, self.run)))

    def test_forbidden_movement_fails(self):
        self.run.events.insert(-1, ToolCallEvent(utc_now(), "tool_call", "S01", {"call_id": "move", "tool_name": "move_forward", "arguments": {}}))
        self.run.events.insert(-1, Event(utc_now(), "tool_result", "S01", {"call_id": "move", "tool_name": "move_forward", "evidence": []}))
        self.assertIn("forbidden_tool:move_forward", failed_names(evaluate(self.scenario, self.run)))

    def test_repeated_tool_requirement_is_not_a_set(self):
        scenario = deepcopy(self.scenario)
        scenario.expected_tools.insert(2, "read_lidar")
        self.assertIn("required_tool:read_lidar", failed_names(evaluate(scenario, self.run)))

    def test_missing_information_acknowledgment_is_required(self):
        scenario = deepcopy(self.scenario)
        scenario.expected_response_requirements["acknowledge_missing"] = True
        self.assertIn("acknowledge_missing", failed_names(evaluate(scenario, self.run)))


class PerspectiveTests(unittest.TestCase):
    def test_user_sensor_and_history_remain_separate_in_an_execution(self):
        scenario = load_scenarios(REGISTRY)[2]
        reading = SensorReading(**scenario.initial_environment_state["readings"][0])
        observed = BeliefState("box_sensor", "box", "color", "brown", "agent_sensor", "camera", .92, reading.observed_at)
        snapshots = [("scenario_start", {"run_id": "perspectives", "name": scenario.name, "execution": "stub"}),
                     ("beliefs_before", {"beliefs": [b.to_dict() for b in scenario.initial_beliefs]}),
                     ("environment_before", {"state": scenario.initial_environment_state}),
                     ("user_query", {"text": scenario.user_query})]
        events = [Event(utc_now(), kind, "S03", payload) for kind, payload in snapshots]
        evidence = [{"evidence_id": "user", "category": "user", "data": scenario.initial_beliefs[0].to_dict()},
                    {"evidence_id": "history", "category": "historical", "data": scenario.initial_beliefs[1].to_dict()}]
        for call_id, name, arguments, result in [
            ("memory", "query_memory", {"subject": "box"}, {"evidence": evidence}),
            ("camera", "read_camera", {"subject": "box"}, {"evidence": [{"evidence_id": "camera", "category": "camera", "data": reading.to_dict()}]}),
            ("update", "update_belief", {"belief": observed.to_dict()}, {"belief": observed.to_dict(), "evidence": []})]:
            events.extend([ToolCallEvent(utc_now(), "tool_call", "S03", {"call_id": call_id, "tool_name": name, "arguments": arguments}),
                           Event(utc_now(), "tool_result", "S03", {"call_id": call_id, "tool_name": name, **result})])
        events.append(BeliefUpdateEvent(utc_now(), "belief_update", "S03", {"call_id": "update", "operation": "upsert", "before": None, "after": observed.to_dict(), "evidence_refs": ["camera"]}))
        events.append(AgentResponseEvent(utc_now(), "agent_response", "S03", {"text": "You report red; camera sees brown; history records blue. These claims disagree.",
                      "evidence_refs": ["user", "history", "camera"], "claims": {"user_color": "red", "sensor_color": "brown", "historical_color": "blue"},
                      "acknowledge_missing": False, "acknowledge_uncertainty": False, "acknowledge_conflict": True}))
        final = deepcopy(scenario.initial_beliefs) + [observed]
        run = TestRunRecord("S03", "perspectives", deepcopy(scenario.initial_beliefs), deepcopy(scenario.initial_environment_state), scenario.user_query, events, final)
        result = evaluate(scenario, run)
        self.assertTrue(result.passed, result.failure_reasons)
        self.assertEqual({b.perspective: b.value for b in final}, {"user": "red", "historical": "blue", "agent_sensor": "brown"})
        run.final_beliefs[0].value = "brown"
        self.assertIn("preserved_perspective:box_user", failed_names(evaluate(scenario, run)))


class DemoTests(unittest.TestCase):
    def test_demo_artifacts_are_parseable_and_repeatable(self):
        command = [sys.executable, str(ROOT / "scripts/run_role4_phase1_demo.py")]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        artifacts = ROOT / "evaluation/logs/role4/phase1"
        def parse_outputs():
            return {path.name: ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                               if path.suffix == ".jsonl" else json.loads(path.read_text(encoding="utf-8")))
                    for path in sorted(artifacts.iterdir()) if path.suffix in {".json", ".jsonl"}}
        before = parse_outputs()
        second = subprocess.run(command, cwd=ROOT.parent, capture_output=True, text=True, check=True)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(remove_timestamps(before), remove_timestamps(parse_outputs()))
        self.assertEqual(len(before), 7)
        self.assertTrue(before["S01_valid_result.json"]["passed"])
        self.assertFalse(before["S01_invalid_result.json"]["passed"])
        self.assertIn("VALID: PASS", first.stdout)
        self.assertIn("INTENTIONALLY INVALID: FAIL", first.stdout)


if __name__ == "__main__":
    unittest.main()
