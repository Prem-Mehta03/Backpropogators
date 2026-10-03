"""Phase B lifecycle, public observation and action-receipt regressions."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from evaluation.role4.contracts.events import ContractError, SensorUnavailable
from evaluation.role4.evaluator import evaluate
from evaluation.role4.integration.adapters.declarative_adapter import DeclarativeAdapter
from evaluation.role4.integration.adapters.sensorimotor_adapter import SensorimotorAdapter
from evaluation.role4.integration.runner import ROOT, load_scenario, run_scenario
from evaluation.role4.integration.trace_recorder import ToolDispatcher, TraceRecorder
from evaluation.role4.policies import load_policies
from evaluation.role4.reference_layers.conflict_procedural_reference import ConflictProceduralReference
from evaluation.role4.reference_layers.declarative_reference import DeclarativeReference
from evaluation.role4.reference_layers.sensorimotor_reference import SensorimotorReference


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in {"timestamp", "evaluated_at"}}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


class PhaseBHarnessTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_scenario("S02")
        self.memory = DeclarativeReference("S02", self.scenario.initial_beliefs)
        self.sensor = SensorimotorReference("S02", self.scenario.initial_environment_state)
        self.procedural = ConflictProceduralReference(
            load_policies()["S02"].execution, self.scenario.initial_environment_state["fixture_time"]
        )
        self.output = ROOT / "evaluation/logs/role4/phase_b/tests" / self._testMethodName

    def execute(self, name="probe"):
        return run_scenario(
            "S02", name, memory_backend=self.memory, procedural_backend=self.procedural,
            sensor_backend=self.sensor, output_dir=self.output,
        )

    def test_reused_backends_reset_each_layer_and_do_not_accumulate_history(self):
        with patch.object(self.memory, "reset", wraps=self.memory.reset) as memory_reset, \
                patch.object(self.sensor, "reset", wraps=self.sensor.reset) as sensor_reset, \
                patch.object(self.procedural, "reset", wraps=self.procedural.reset) as procedural_reset:
            first = self.execute()
            history = self.memory.get_belief_history("path_a", "status")
            self.assertGreater(len(history), 0)
            second = self.execute()
        self.assertEqual(first.status, "PASS")
        self.assertEqual(second.status, "PASS")
        for spy in (memory_reset, sensor_reset, procedural_reset):
            self.assertEqual(spy.call_count, 2)
            self.assertEqual(spy.call_args.args, ("S02",))
        self.assertEqual(history, self.memory.get_belief_history("path_a", "status"))
        self.assertEqual(stable(first.run.to_dict()), stable(second.run.to_dict()))

    def test_public_snapshots_and_call_evidence_pairs_match_recorded_run(self):
        run = self.execute().run
        returns = [e.payload for e in run.events if e.event_type == "boundary_result"]
        snapshots = [p["response"] for p in returns if p["operation"] == "get_belief_snapshot"]
        self.assertEqual(snapshots[0], [b.to_dict() for b in run.initial_beliefs])
        self.assertEqual(snapshots[-1], [b.to_dict() for b in run.final_beliefs])
        environment = next(p["response"] for p in returns if p["operation"] == "get_environment_state")
        self.assertEqual(environment, run.initial_environment_state)
        calls = {e.payload["call_id"] for e in run.events if e.event_type == "tool_call"}
        results = [e.payload for e in run.events if e.event_type == "tool_result"]
        self.assertEqual(calls, {p["call_id"] for p in results})
        evidence = [item["evidence_id"] for p in results for item in p["evidence"]]
        self.assertEqual(len(evidence), len(set(evidence)))
        response = next(e.payload for e in run.events if e.event_type == "agent_response")
        self.assertTrue(set(response["evidence_refs"]) <= set(evidence))

    def test_unavailable_existing_sensor_aborts_without_factual_response_or_update(self):
        with patch.object(self.sensor, "read_lidar", side_effect=SensorUnavailable("Offline probe unavailable")):
            outcome = self.execute("unavailable")
        self.assertEqual(outcome.status, "CONTRACT ERROR")
        self.assertIsNone(outcome.run)
        self.assertFalse(outcome.error["evaluated"])
        self.assertEqual(outcome.error["error_type"], "SensorUnavailable")
        trace = [json.loads(line) for line in (self.output / "S02_unavailable_trace.jsonl").read_text().splitlines()]
        self.assertFalse(any(e["event_type"] in {"agent_response", "belief_update"} for e in trace))
        self.assertFalse(any(e["event_type"] == "tool_result" and e["payload"]["tool_name"] == "read_lidar" for e in trace))
        self.assertEqual(self.memory.get_belief_snapshot(), [b.to_dict() for b in self.scenario.initial_beliefs])

    def test_malformed_payload_then_reuse_recovers_with_fresh_trace_and_initial_state(self):
        original = self.sensor.read_lidar()
        malformed = {k: v for k, v in original.items() if k != "confidence"}
        with patch.object(self.sensor, "read_lidar", return_value=malformed):
            failed = self.execute("malformed")
        recovered = self.execute("recovered")
        self.assertEqual(failed.status, "CONTRACT ERROR")
        self.assertIn("confidence", failed.error["message"])
        self.assertEqual(recovered.status, "PASS")
        self.assertEqual(recovered.run.initial_beliefs, self.scenario.initial_beliefs)
        self.assertFalse(any(e.event_type in {"tool_error", "contract_error"} for e in recovered.run.events))
        self.assertEqual(next(e.payload["call_id"] for e in recovered.run.events if e.event_type == "tool_call"), "call_001")

    def test_empty_public_memory_query_has_no_positive_or_negative_fact_evidence(self):
        recorder = TraceRecorder("S02")
        gateway = ToolDispatcher(DeclarativeAdapter(self.memory), SensorimotorAdapter(self.sensor), recorder)
        result = gateway.call("query_memory", {"subject": "absent_subject", "predicate": "status"})
        self.assertEqual(result["beliefs"], [])
        self.assertEqual(result["evidence"], [])
        self.assertNotIn("value", result)
        with self.assertRaises(ContractError):
            recorder.require_evidence(["invented_lookup_fact"])

    def test_rejected_action_receipt_is_explicit_and_false_execution_is_detected(self):
        scenario = load_scenario("S08")
        sensor = SensorimotorReference("S08", scenario.initial_environment_state)
        with patch.object(sensor, "move_forward", create=True) as physical:
            run = run_scenario(
                "S08", "rejected", sensor_backend=sensor,
                injected_fault="trust_user_and_move", output_dir=self.output,
            ).run
        physical.assert_not_called()
        receipt = next(e.payload for e in run.events if e.event_type == "tool_result" and e.payload["tool_name"] == "move_forward")
        self.assertFalse(receipt["authorized"])
        self.assertFalse(receipt["executed"])
        self.assertEqual(receipt["state"], "rejected")
        corrupted = deepcopy(run)
        next(e.payload for e in corrupted.events if e.event_type == "tool_result" and e.payload["tool_name"] == "move_forward")["executed"] = True
        result = evaluate(scenario, corrupted, load_policies()["S08"])
        self.assertFalse(next(c["passed"] for c in result.checks if c["name"] == "trace_integrity"))

    def test_deferred_cases_have_no_execution_path_in_phase_b(self):
        for scenario in ("S07", "S09", "S06", "S10"):
            with self.subTest(scenario=scenario), self.assertRaises(ContractError):
                run_scenario(scenario, output_dir=self.output)


if __name__ == "__main__":
    unittest.main()
