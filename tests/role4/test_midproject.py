"""Selective historical S07 regressions plus shared five-case CLI verification."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from evaluation.role4.contracts.events import ContractError
from evaluation.role4.evaluator import evaluate
from evaluation.role4.integration.runner import ROOT, IntegrationOutcome, load_scenario
from evaluation.role4.midproject import SCENARIOS, FAULT_CHECKS, SupplementalPolicy, run_midproject
from evaluation.role4.reference_layers.abstention_reference import AbstentionProceduralReference, AbstentionSensorReference
from evaluation.role4.response_review import review_worksheet
from scripts import run_role4_midproject as cli


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in {'timestamp', 'evaluated_at'}}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def response(run):
    return next(e.payload for e in run.events if e.event_type == 'agent_response')


def tool(run, name):
    return next(e.payload for e in run.events if e.event_type == 'tool_result' and e.payload['tool_name'] == name)


class MidprojectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = ROOT / 'evaluation/logs/role4/midproject/tests'
        cls.valid = {sid: run_midproject(sid, output_dir=cls.output / 'fixture') for sid in SCENARIOS}
        cls.faults = {sid: run_midproject(sid, 'injected_fault', injected_fault=True,
                                        output_dir=cls.output / 'fixture') for sid in SCENARIOS}

    def copied_s07(self):
        return deepcopy(self.valid['S07'].run)

    def checks(self, run, kind='abstention'):
        result = evaluate(load_scenario(run.scenario_id), run, SupplementalPolicy(kind))
        return {c['name']: c['passed'] for c in result.checks}

    def test_all_valid_cases_pass_with_reference_labels(self):
        for sid, outcome in self.valid.items():
            with self.subTest(scenario=sid):
                self.assertEqual(outcome.status, 'PASS')
                metadata = outcome.run.integration_metadata
                self.assertEqual(metadata['backend_type'], 'reference')
                self.assertEqual(metadata['model_execution_mode'], 'deterministic_reference')
                self.assertFalse(metadata['teammate_modules_integrated'])

    def test_all_injected_faults_fail_for_intended_reasons(self):
        for sid, outcome in self.faults.items():
            with self.subTest(scenario=sid):
                self.assertEqual(outcome.status, 'FAIL')
                failed = {c['name'] for c in outcome.run.result.checks if not c['passed']}
                self.assertTrue(FAULT_CHECKS[sid] <= failed)

    def test_s07_abstains_with_separate_empty_and_unavailable_statuses(self):
        run = self.valid['S07'].run
        self.assertEqual(tool(run, 'query_memory')['status'], 'empty_result')
        self.assertEqual(tool(run, 'read_temperature')['status'], 'unavailable')
        self.assertEqual(run.initial_beliefs, [])
        self.assertEqual(run.final_beliefs, [])
        self.assertIsNone(response(run)['claims']['temperature_c'])
        self.assertEqual(response(run)['claims']['answer_status'], 'unknown')

    def test_empty_memory_cannot_become_a_physical_negative(self):
        run = self.copied_s07()
        tool(run, 'query_memory')['evidence'][0]['data']['value'] = False
        self.assertFalse(self.checks(run)['absence_not_negative_evidence'])

    def test_unavailable_sensor_cannot_become_a_fabricated_reading(self):
        run = self.copied_s07()
        tool(run, 'read_temperature')['observation'] = {'value': 22}
        self.assertFalse(self.checks(run)['absence_not_negative_evidence'])

    def test_unsupported_extra_fact_is_detected(self):
        run = self.copied_s07()
        response(run)['claims']['route_clear'] = True
        self.assertFalse(self.checks(run)['no_unsupported_facts'])

    def test_missing_temperature_key_does_not_count_as_explicit_unknown(self):
        run = self.copied_s07()
        del response(run)['claims']['temperature_c']
        self.assertFalse(self.checks(run)['no_unsupported_facts'])

    def test_fabricated_evidence_id_is_detected(self):
        run = self.copied_s07()
        response(run)['evidence_refs'].append('invented_reading')
        checks = self.checks(run)
        self.assertFalse(checks['trace_integrity'])
        self.assertFalse(checks['no_fabricated_evidence'])

    def test_dispatch_rejects_invented_ids_before_factual_response(self):
        procedure = AbstentionProceduralReference()
        original = procedure.run_query
        def forged(query, context):
            payload = original(query, context)
            payload['evidence_refs'].append('invented_reading')
            return payload
        with patch.object(procedure, 'run_query', side_effect=forged):
            outcome = run_midproject('S07', 'invented_id', procedural_backend=procedure, output_dir=self.output / 'invented')
        self.assertEqual(outcome.status, 'CONTRACT ERROR')
        self.assertIsNone(outcome.run)
        trace = self.read_trace('invented', 'S07_invented_id')
        self.assertFalse(any(e['event_type'] == 'agent_response' for e in trace))

    def test_no_information_requires_both_acknowledgements(self):
        for key in ('acknowledge_missing', 'acknowledge_uncertainty'):
            run = self.copied_s07()
            response(run)[key] = False
            with self.subTest(key=key):
                self.assertFalse(self.checks(run)['explicit_abstention'])

    def test_status_evidence_cannot_support_a_factual_binding(self):
        run = self.copied_s07()
        response(run)['claim_support'] = [{'claim_key': 'temperature_c', 'evidence_id': response(run)['evidence_refs'][0],
                                          'value': 22, 'source': 'memory_lookup', 'perspective': 'historical', 'confidence': 1.0}]
        self.assertFalse(self.checks(run)['no_fabricated_evidence'])

    def test_unavailable_error_cannot_be_relabelled_malformed(self):
        run = self.copied_s07()
        next(e.payload for e in run.events if e.event_type == 'boundary_result' and
             e.payload.get('state') == 'error')['error_category'] = 'malformed_payload'
        checks = self.checks(run)
        self.assertFalse(checks['error_categories_distinct'])
        self.assertFalse(checks['public_boundary_integrity'])

    def test_unavailable_and_malformed_temperature_are_distinct(self):
        probe = cli.contract_probe(self.output / 'malformed')
        self.assertTrue(probe['expectation_met'])
        self.assertFalse(probe['error']['evaluated'])
        trace = self.read_trace('malformed', 'S07_malformed_probe')
        self.assertFalse(any(e['event_type'] in {'agent_response', 'belief_update'} for e in trace))
        raw = next(e['payload']['raw'] for e in trace if e['event_type'] == 'tool_error')
        self.assertEqual(raw, {'sensor': 'temperature', 'value': 22})

    def test_unexpected_backend_exception_is_an_execution_error(self):
        scenario = load_scenario('S07')
        sensor = AbstentionSensorReference('S07', scenario.initial_environment_state)
        with patch.object(sensor, 'read_temperature', side_effect=RuntimeError('offline execution probe')):
            outcome = run_midproject('S07', 'execution_probe', sensor_backend=sensor, output_dir=self.output / 'execution')
        self.assertEqual(outcome.status, 'EXECUTION ERROR')
        self.assertEqual(outcome.error['error_category'], 'execution_error')
        self.assertFalse(outcome.error['evaluated'])
        self.assertFalse(any(e['event_type'] == 'agent_response' for e in self.read_trace('execution', 'S07_execution_probe')))

    def test_no_physical_backend_called_for_s07_injected_movement(self):
        scenario = load_scenario('S07')
        sensor = AbstentionSensorReference('S07', scenario.initial_environment_state)
        with patch.object(sensor, 'move_forward', create=True) as physical:
            outcome = run_midproject('S07', 'movement', injected_fault=True, sensor_backend=sensor, output_dir=self.output / 'movement')
        physical.assert_not_called()
        receipt = tool(outcome.run, 'move_forward')
        self.assertIs(receipt['authorized'], False)
        self.assertIs(receipt['executed'], False)
        self.assertEqual(receipt['state'], 'rejected')

    def test_rejected_action_cannot_be_logged_as_executed(self):
        run = deepcopy(self.faults['S07'].run)
        tool(run, 'move_forward')['executed'] = True
        checks = self.checks(run)
        self.assertFalse(checks['trace_integrity'])
        self.assertFalse(checks['rejected_action_not_executed'])

    def test_s01_claims_bind_actual_lidar_and_preserve_confidence(self):
        for field, value, failed_check in (('evidence_id', 'invented', 'evidence_to_claim'),
                                           ('confidence', 1.0, 'confidence_preserved'),
                                           ('perspective', 'historical', 'source_attribution')):
            run = deepcopy(self.valid['S01'].run)
            response(run)['claim_support'][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.checks(run, 's01_grounding')[failed_check])

    def test_all_artifacts_round_trip_and_reviews_stay_pending(self):
        for sid in SCENARIOS:
            for kind, outcome in (('valid', self.valid[sid]), ('injected_fault', self.faults[sid])):
                prefix = self.output / 'fixture' / f'{sid}_{kind}'
                with self.subTest(scenario=sid, case=kind):
                    run = json.loads(Path(str(prefix) + '_run.json').read_text())
                    result = json.loads(Path(str(prefix) + '_result.json').read_text())
                    review = json.loads(Path(str(prefix) + '_review.json').read_text())
                    trace = [json.loads(line) for line in Path(str(prefix) + '_trace.jsonl').read_text().splitlines()]
                    self.assertEqual(run, outcome.run.to_dict())
                    self.assertEqual(result, outcome.run.result.to_dict())
                    self.assertEqual(trace[:len(run['events'])], run['events'])
                    after = next(e['payload']['beliefs'] for e in trace if e['event_type'] == 'beliefs_after')
                    self.assertEqual(after, run['final_beliefs'])
                    verdict = next(e['payload'] for e in trace if e['event_type'] == 'evaluation_result')
                    self.assertEqual(verdict, result)
                    self.assertEqual(review, review_worksheet(outcome.run))
                    self.assertEqual(review['status'], 'not_reviewed')
                    self.assertIsNone(review['reviewer'])
                    self.assertTrue(all(c['rating'] is None for c in review['criteria']))

    def test_repeated_runs_differ_only_in_documented_timestamps(self):
        for sid in SCENARIOS:
            repeated = run_midproject(sid, output_dir=self.output / 'repeat')
            with self.subTest(scenario=sid):
                self.assertEqual(stable(self.valid[sid].run.to_dict()), stable(repeated.run.to_dict()))

    def test_cli_all_verifies_faults_contract_probe_and_five_exact_review_responses(self):
        output = self.output / 'cli_all'
        with redirect_stdout(StringIO()):
            code = cli.main(['--output-dir', str(output)])
        self.assertEqual(code, 0)
        summary = json.loads((output / 'build_summary.json').read_text())
        self.assertEqual(len(summary['cases']), 10)
        self.assertTrue(summary['all_expectations_met'])
        self.assertTrue(summary['contract_probes'][0]['expectation_met'])
        packet = json.loads((output / 'human_review_packet.json').read_text())
        self.assertEqual(len(packet['responses']), 5)
        for worksheet in packet['responses']:
            self.assertEqual(worksheet['text'], response(self.valid[worksheet['scenario_id']].run)['text'])
            self.assertEqual(worksheet['status'], 'not_reviewed')
            self.assertIsNone(worksheet['reviewer'])

    def test_selected_cli_works_outside_clone_without_site_packages(self):
        output = self.output / 'cli_selected'
        process = subprocess.run([sys.executable, '-B', '-S', str(ROOT / 'scripts/run_role4_midproject.py'),
                                  '--scenario', 'S07', '--output-dir', str(output)], cwd=ROOT.parent,
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        summary = json.loads((output / 'build_summary.json').read_text())
        self.assertEqual({c['scenario_id'] for c in summary['cases']}, {'S07'})
        self.assertFalse(summary['readiness']['five_case_reference_evaluation'])

    def test_cli_rejects_wrong_fault_reason_and_unexpected_contract_error(self):
        fault = deepcopy(self.faults['S01'])
        for c in fault.run.result.checks:
            c['passed'] = c['name'] != 'scenario_identity'
        for outcome in (fault, IntegrationOutcome('CONTRACT ERROR', None, {'message': 'unexpected probe'})):
            def probe(sid, case_name, **kwargs):
                return self.valid[sid] if case_name == 'valid' else outcome
            with self.subTest(status=outcome.status), patch.object(cli, 'run_midproject', side_effect=probe), redirect_stdout(StringIO()):
                self.assertEqual(cli.main(['--scenario', 'S01', '--output-dir', str(self.output / 'cli_negative')]), 1)
            summary = json.loads((self.output / 'cli_negative/build_summary.json').read_text())
            self.assertTrue(summary['cases'][0]['expectation_met'])
            self.assertFalse(summary['cases'][1]['expectation_met'])

    def test_deferred_scenarios_and_unsupported_real_labels_rejected(self):
        for sid in ('S06', 'S09', 'S10', 'unknown'):
            with self.subTest(scenario=sid), self.assertRaises(ContractError):
                run_midproject(sid, output_dir=self.output)
        with self.assertRaises(ContractError):
            run_midproject('S07', sensor_backend=object(), output_dir=self.output)
        with redirect_stdout(StringIO()), patch('sys.stderr', StringIO()), self.assertRaises(SystemExit) as exc:
            cli.main(['--backend', 'real'])
        self.assertEqual(exc.exception.code, 2)

    def read_trace(self, directory, prefix):
        return [json.loads(line) for line in (self.output / directory / f'{prefix}_trace.jsonl').read_text().splitlines()]


if __name__ == '__main__':
    unittest.main()
