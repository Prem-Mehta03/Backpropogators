"""Contract rejection, live boundary instrumentation and reference integration checks."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

from evaluation.role4.contracts.declarative import DeclarativePort
from evaluation.role4.contracts.events import (ContractError, ResponseMetadata, SensorUnavailable,
                              belief_from_payload, sensor_from_payload)
from evaluation.role4.contracts.procedural import ProceduralPort, QueryContext
from evaluation.role4.contracts.sensorimotor import SensorimotorPort
from evaluation.role4.logger import read_events
from evaluation.role4.integration.adapters.declarative_adapter import DeclarativeAdapter
from evaluation.role4.integration.adapters.procedural_adapter import ProceduralAdapter
from evaluation.role4.integration.adapters.sensorimotor_adapter import SensorimotorAdapter
from evaluation.role4.integration.runner import ROOT, load_s01, reference_backends, run_s01
from evaluation.role4.integration.trace_recorder import TraceRecorder, ToolDispatcher


def without_times(value):
    if isinstance(value, dict):
        return {k: without_times(v) for k, v in value.items() if k not in {"timestamp", "evaluated_at"}}
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_s01()
        self.memory_backend, self.procedural_backend, self.sensor_backend = reference_backends(self.scenario)
        self.memory = DeclarativeAdapter(self.memory_backend)
        self.sensors = SensorimotorAdapter(self.sensor_backend)
        self.procedural = ProceduralAdapter(self.procedural_backend)
        self.belief = self.scenario.initial_beliefs[0].to_dict()
        self.sensor = self.sensor_backend.read_lidar()

    def test_adapters_satisfy_all_shared_ports(self):
        for adapter, protocol in [(self.memory, DeclarativePort), (self.sensors, SensorimotorPort), (self.procedural, ProceduralPort)]:
            with self.subTest(protocol=protocol):
                self.assertIsInstance(adapter, protocol)

    def test_valid_belief_conversion(self):
        self.assertEqual(belief_from_payload(self.belief), self.scenario.initial_beliefs[0])

    def test_missing_belief_fields(self):
        for field in self.belief:
            with self.subTest(field=field):
                raw = deepcopy(self.belief)
                del raw[field]
                with self.assertRaisesRegex(ContractError, field):
                    belief_from_payload(raw)

    def test_invalid_belief_confidence(self):
        for confidence in (-.1, 1.1, True, float('nan'), float('inf'), "0.9"):
            with self.subTest(confidence=confidence):
                raw = {**self.belief, "confidence": confidence}
                with self.assertRaises(ContractError):
                    belief_from_payload(raw)

    def test_invalid_belief_perspective(self):
        with self.assertRaisesRegex(ContractError, "perspective"):
            belief_from_payload({**self.belief, "perspective": "global"})

    def test_null_source_is_preserved_as_unverified(self):
        self.assertIsNone(belief_from_payload({**self.belief, "source": None}).source)

    def test_valid_sensor_conversion(self):
        observed = sensor_from_payload(self.sensor, "lidar")
        self.assertEqual(observed.evidence_id, "lidar_evidence")
        self.assertEqual(observed.unit, "cm")
        self.assertEqual(observed.environment_revision, 1)
        self.assertEqual(observed.reading.details["distance_cm"], 12)

    def test_each_missing_sensor_field(self):
        for field in self.sensor:
            with self.subTest(field=field):
                raw = deepcopy(self.sensor)
                del raw[field]
                with self.assertRaisesRegex(ContractError, field):
                    sensor_from_payload(raw)

    def test_sensor_confidence_out_of_range(self):
        for value in (-1, 2, True, "high", float('nan')):
            with self.subTest(confidence=value):
                with self.assertRaises(ContractError):
                    sensor_from_payload({**self.sensor, "confidence": value})

    def test_invalid_and_missing_timestamps(self):
        for converter, raw in [(belief_from_payload, self.belief), (sensor_from_payload, self.sensor)]:
            for time in (None, "yesterday", "2026-10-02T09:00:00"):
                with self.subTest(converter=converter.__name__, time=time):
                    with self.assertRaisesRegex(ContractError, "timestamp"):
                        converter({**raw, "observed_at": time})

    def test_offset_timestamps_normalize_to_utc(self):
        result = belief_from_payload({**self.belief, "observed_at": "2026-10-02T14:29:00+05:30"})
        self.assertEqual(result.observed_at, self.belief["observed_at"])

    def test_wrong_units_and_sensor_name(self):
        with self.assertRaisesRegex(ContractError, "unit"):
            sensor_from_payload({**self.sensor, "unit": "m"})
        with self.assertRaisesRegex(ContractError, "Expected sensor"):
            sensor_from_payload(self.sensor, "camera")

    def test_invalid_sensor_revisions(self):
        for revision in (0, -1, True, 1.0, "1"):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(ContractError, "revision"):
                    sensor_from_payload({**self.sensor, "environment_revision": revision})

    def test_response_requires_all_metadata(self):
        raw = {"text": "Blocked", "evidence_refs": [], "claims": {"path_status": "blocked"},
               "acknowledge_conflict": True, "acknowledge_uncertainty": False, "acknowledge_missing": False}
        self.assertEqual(ResponseMetadata.from_payload(raw).to_dict(), raw)
        for key in raw:
            broken = deepcopy(raw)
            del broken[key]
            with self.subTest(field=key), self.assertRaises(ContractError):
                ResponseMetadata.from_payload(broken)

    def test_response_invalid_flag_rejected(self):
        raw = {"text": "Blocked", "evidence_refs": [], "claims": {}, "acknowledge_conflict": "yes",
               "acknowledge_uncertainty": False, "acknowledge_missing": False}
        with self.assertRaisesRegex(ContractError, "boolean"):
            ResponseMetadata.from_payload(raw)

    def test_adapter_snapshot_is_detached(self):
        first = self.memory.get_belief_snapshot()
        first[0].value = "blocked"
        self.assertEqual(self.memory.get_belief_snapshot()[0].value, "clear")

    def test_raw_memory_debug_data_preserved(self):
        raw = {**self.belief, "extra_layer_metadata": {"row": 10}}
        self.memory_backend.get_belief_snapshot = lambda: [deepcopy(raw)]
        self.memory.get_belief_snapshot()
        self.assertEqual(self.memory.last_raw[0]["extra_layer_metadata"], {"row": 10})

    def test_duplicate_belief_ids_rejected(self):
        self.memory_backend.get_belief_snapshot = lambda: [deepcopy(self.belief), deepcopy(self.belief)]
        with self.assertRaisesRegex(ContractError, "Duplicate belief"):
            self.memory.get_belief_snapshot()

    def test_query_checks_subject_and_predicate(self):
        self.memory_backend.get_beliefs = lambda subject, predicate: [deepcopy(self.belief)]
        with self.assertRaisesRegex(ContractError, "another subject"):
            self.memory.get_beliefs("wrong", "status")

    def test_history_and_previous_value_are_preserved(self):
        current = belief_from_payload({**self.belief, "belief_id": "path_a_sensor", "perspective": "agent_sensor", "source": "lidar"})
        self.memory.upsert_belief(current, ["reading1"])
        changed = belief_from_payload({**current.to_dict(), "value": "blocked"})
        receipt = self.memory.upsert_belief(changed, ["reading2"])
        self.assertEqual(receipt.before.value, "clear")
        self.assertEqual(receipt.after.value, "blocked")
        history = self.memory.get_belief_history("path_a", "status")
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1].evidence_refs, ["reading2"])
        self.assertEqual(history[-1].before.value, "clear")
        self.assertEqual(self.memory.get_belief_snapshot()[0].value, "clear")

    def test_historical_overwrite_rejected_before_commit(self):
        changed = belief_from_payload({**self.belief, "value": "blocked"})
        with self.assertRaisesRegex(ContractError, "Historical belief is immutable"):
            self.memory.upsert_belief(changed, ["reading"])
        self.assertEqual(self.memory.get_belief_snapshot()[0].value, "clear")

    def test_update_requires_evidence_references(self):
        with self.assertRaisesRegex(ContractError, "nonempty"):
            self.memory.upsert_belief(self.scenario.initial_beliefs[0], [])

    def test_bad_committed_receipt_rejected(self):
        self.memory_backend.upsert_belief = lambda belief, refs: {"before": None, "after": belief, "evidence_refs": ["wrong"]}
        current = belief_from_payload({**self.belief, "belief_id": "sensor", "perspective": "agent_sensor"})
        with self.assertRaisesRegex(ContractError, "receipt"):
            self.memory.upsert_belief(current, ["reading"])

    def test_false_commit_without_snapshot_change_rejected(self):
        self.memory_backend.upsert_belief = lambda belief, refs: {"before": None, "after": belief, "evidence_refs": refs}
        current = belief_from_payload({**self.belief, "belief_id": "sensor", "perspective": "agent_sensor"})
        with self.assertRaisesRegex(ContractError, "snapshot"):
            self.memory.upsert_belief(current, ["reading"])

    def test_sensor_revision_mismatch_rejected(self):
        self.sensor_backend.read_lidar = lambda: {**self.sensor, "environment_revision": 2}
        with self.assertRaisesRegex(ContractError, "revision differs"):
            self.sensors.read_lidar()

    def test_environment_snapshot_and_revision(self):
        self.assertEqual(self.sensors.get_environment_state(), self.scenario.initial_environment_state)
        self.assertEqual(self.sensors.get_environment_revision(), 1)
        invalid = deepcopy(self.scenario.initial_environment_state)
        invalid["readings"][0]["confidence"] = 2
        self.sensor_backend.get_environment_state = lambda: invalid
        with self.assertRaisesRegex(ContractError, "confidence"):
            self.sensors.get_environment_state()

    def test_camera_unavailable_is_explicit(self):
        with self.assertRaises(SensorUnavailable):
            self.sensors.read_camera()

    def test_invalid_environment_revision_rejected(self):
        self.sensor_backend.get_environment_revision = lambda: True
        with self.assertRaisesRegex(ContractError, "positive integer"):
            self.sensors.get_environment_revision()

    def test_reference_reset_restores_initial_memory(self):
        current = belief_from_payload({**self.belief, "belief_id": "sensor", "perspective": "agent_sensor"})
        self.memory.upsert_belief(current, ["reading"])
        self.memory.reset("S01")
        self.assertEqual(self.memory.get_belief_snapshot(), self.scenario.initial_beliefs)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.recorder = TraceRecorder("S01")
        self.item = {"evidence_id": "reading", "category": "lidar", "data": {"value": "blocked"}}

    def test_duplicate_tool_call_ids(self):
        self.recorder.begin_tool("read_lidar", {}, "same")
        with self.assertRaisesRegex(ContractError, "Duplicate tool call ID"):
            self.recorder.begin_tool("read_lidar", {}, "same")

    def test_unmatched_tool_result(self):
        with self.assertRaisesRegex(ContractError, "Unmatched tool result"):
            self.recorder.tool_result("missing", "read_lidar", {"evidence": []})

    def test_wrong_tool_name_in_return(self):
        call = self.recorder.begin_tool("read_lidar", {})
        with self.assertRaisesRegex(ContractError, "Unmatched"):
            self.recorder.tool_result(call, "read_camera", {"evidence": []})
        with self.assertRaisesRegex(ContractError, "override"):
            self.recorder.tool_result(call, "read_lidar", {"evidence": [], "call_id": "forged"})

    def test_duplicate_evidence_ids_across_returns(self):
        first = self.recorder.begin_tool("read_lidar", {})
        self.recorder.tool_result(first, "read_lidar", {"evidence": [self.item]})
        second = self.recorder.begin_tool("read_lidar", {})
        with self.assertRaisesRegex(ContractError, "Duplicate evidence"):
            self.recorder.tool_result(second, "read_lidar", {"evidence": [self.item]})

    def test_duplicate_evidence_ids_in_one_return(self):
        call = self.recorder.begin_tool("read_lidar", {})
        with self.assertRaisesRegex(ContractError, "Duplicate evidence"):
            self.recorder.tool_result(call, "read_lidar", {"evidence": [self.item, self.item]})

    def test_unknown_evidence_rejected(self):
        with self.assertRaisesRegex(ContractError, "Unknown evidence"):
            self.recorder.require_evidence(["invented"])

    def test_duplicate_evidence_references(self):
        with self.assertRaisesRegex(ContractError, "Duplicate evidence_refs"):
            self.recorder.require_evidence(["reading", "reading"])

    def test_finish_requires_response(self):
        with self.assertRaisesRegex(ContractError, "Incomplete"):
            self.recorder.finish()

    def test_raw_non_json_error_can_still_be_logged(self):
        call = self.recorder.begin_tool("read_lidar", {})
        self.recorder.tool_error(call, "read_lidar", ContractError("bad raw payload"), {"values": {1, 2}})
        json.dumps(self.recorder.events[-1].to_dict())

    def test_tool_after_final_response_rejected(self):
        metadata = ResponseMetadata("Unknown", [], {}, False, True, True)
        self.recorder.response(metadata)
        with self.assertRaisesRegex(ContractError, "after the final response"):
            self.recorder.begin_tool("read_lidar", {})


class IntegrationTests(unittest.TestCase):
    def run_case(self, name="test", **faults):
        scenario = load_s01()
        with tempfile.TemporaryDirectory() as directory:
            return run_s01(name, *reference_backends(scenario, **faults), output_dir=directory)

    def test_valid_integrated_s01(self):
        outcome = self.run_case()
        self.assertEqual(outcome.status, "PASS")
        self.assertEqual(len(outcome.run.result.checks), 20)
        self.assertEqual([e.payload["tool_name"] for e in outcome.run.events if e.event_type == "tool_call"], ["query_memory", "read_lidar", "update_belief"])
        self.assertEqual({b.perspective: b.value for b in outcome.run.final_beliefs}, {"historical": "clear", "agent_sensor": "blocked"})

    def test_no_lidar_execution_fails(self):
        outcome = self.run_case(skip_lidar=True)
        self.assertEqual(outcome.status, "FAIL")
        reasons = '\n'.join(outcome.run.result.failure_reasons)
        self.assertIn("required_tool:read_lidar", reasons)
        self.assertIn("response_evidence", reasons)
        self.assertIn("required_update:path_a_sensor", reasons)
        self.assertEqual(len(outcome.run.result.failure_reasons), 9)

    def test_malformed_sensor_never_reaches_evaluator(self):
        with patch("evaluation.role4.integration.runner.evaluate") as evaluator:
            outcome = self.run_case(malformed_lidar=True)
        evaluator.assert_not_called()
        self.assertEqual(outcome.status, "CONTRACT ERROR")
        self.assertIsNone(outcome.run)
        self.assertIn("confidence", outcome.error["message"])
        self.assertFalse(outcome.error["evaluated"])

    def test_maximum_step_handling(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome = run_s01("step_limit", *reference_backends(load_s01()), output_dir=directory, max_steps=1)
        self.assertEqual(outcome.status, "CONTRACT ERROR")
        self.assertIn("Maximum tool steps", outcome.error["message"])

    def test_boundary_events_exist_before_backend_invocation(self):
        scenario = load_s01()
        raw_memory, _, raw_sensors = reference_backends(scenario)
        recorder = TraceRecorder("S01")
        memory, sensors = DeclarativeAdapter(raw_memory), SensorimotorAdapter(raw_sensors)
        gateway = ToolDispatcher(memory, sensors, recorder)
        original = raw_sensors.read_lidar
        def observed_read():
            self.assertEqual(recorder.events[-1].event_type, "tool_call")
            self.assertEqual(recorder.events[-1].payload["tool_name"], "read_lidar")
            return original()
        raw_sensors.read_lidar = observed_read
        gateway.call("read_lidar", {})
        self.assertEqual([e.event_type for e in recorder.events], ["tool_call", "tool_result"])

    def test_changed_sensor_data_changes_committed_state_and_evaluation(self):
        scenario = load_s01()
        memory, procedural, sensors = reference_backends(scenario)
        original = sensors.read_lidar
        sensors.read_lidar = lambda: {**original(), "value": "clear"}
        with tempfile.TemporaryDirectory() as directory:
            outcome = run_s01("changed", memory, procedural, sensors, output_dir=directory)
        self.assertEqual(outcome.status, "FAIL")
        self.assertEqual(outcome.run.final_beliefs[-1].value, "clear")
        self.assertFalse(outcome.run.events[-1].payload["acknowledge_conflict"])

    def test_artifacts_parse_and_partial_contract_trace_is_honest(self):
        scenario = load_s01()
        with tempfile.TemporaryDirectory() as directory:
            for name, faults in [("valid", {}), ("missing", {"skip_lidar": True}), ("bad", {"malformed_lidar": True})]:
                run_s01(name, *reference_backends(scenario, **faults), output_dir=directory)
            for path in Path(directory).iterdir():
                if path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
                else:
                    read_events(path)
            error_events = read_events(Path(directory) / "S01_bad_trace.jsonl")
            self.assertEqual(error_events[-1].event_type, "contract_error")
            self.assertFalse(any(e.event_type in {"agent_response", "evaluation_result", "belief_update"} for e in error_events))
            raw_error = next(e.payload["raw"] for e in error_events if e.event_type == "tool_error")
            self.assertNotIn("confidence", raw_error)

    def test_phase2_demo_is_repeatable_from_another_directory(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/run_role4_phase2_demo.py")]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        def parse_artifacts():
            return {p.name: ([json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()] if p.suffix == '.jsonl' else json.loads(p.read_text(encoding='utf-8')))
                    for p in sorted((ROOT / 'evaluation/logs/role4/phase2').iterdir()) if p.suffix in {'.json', '.jsonl'}}
        before = parse_artifacts()
        second = subprocess.run(command, cwd=ROOT.parent, capture_output=True, text=True, check=True)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(without_times(before), without_times(parse_artifacts()))
        self.assertIn("Case A (integrated_valid): PASS", first.stdout)
        self.assertIn("Case B (missing_lidar): FAIL", first.stdout)
        self.assertIn("Case C (malformed_sensor): CONTRACT ERROR", first.stdout)
        self.assertFalse(before['summary.json']['teammate_modules_integrated'])


if __name__ == '__main__':
    unittest.main()
