"""Five-case Phase C reference evaluation; valid passes and intended fault failures are expected."""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.role4.integration.runner import load_scenario
from evaluation.role4.logger import write_json
from evaluation.role4.midproject import SCENARIOS, FAULTS, FAULT_CHECKS, SCOPE, run_midproject
from evaluation.role4.reference_layers.abstention_reference import AbstentionSensorReference
from evaluation.role4.response_review import review_worksheet

CLIENT_STATUS = 'Real client compatibility tested; single-tool execution and complete agent integration pending.'


def dependency_status():
    missing = []
    for parent, child in (('contracts', 'contracts.models'), ('sensorimotor', 'sensorimotor.stub')):
        try:
            present = importlib.util.find_spec(parent) is not None and importlib.util.find_spec(child) is not None
        except (ImportError, ValueError):
            present = False
        if not present:
            missing.append(child)
    return {'missing_inputs': missing, 'collection_blockers':
            ['tests.procedural.test_single_tool_call', 'tests.procedural.test_tools'] if missing else [],
            'complete_agent_api': 'not_supplied', 'client_status': CLIENT_STATUS}


def case_record(scenario_id, kind, outcome, output):
    valid = kind == 'valid'
    result = outcome.run.result.to_dict() if outcome.run else None
    failed = {c['name'] for c in result['checks'] if not c['passed']} if result else set()
    required = set() if valid else FAULT_CHECKS[scenario_id]
    prefix = f'{scenario_id}_{kind}'
    scenario = load_scenario(scenario_id)
    record = {'scenario_id': scenario_id, 'case': kind, 'fault_demonstration': not valid,
              'injected_fault': None if valid else FAULTS[scenario_id], 'backend_type': 'reference',
              'model_execution_mode': 'deterministic_reference', 'integration_scope': SCOPE,
              'expected_status': 'PASS' if valid else 'FAIL', 'status': outcome.status,
              'expectation_met': outcome.status == ('PASS' if valid else 'FAIL') and required <= failed,
              'required_failure_checks': sorted(required), 'failed_checks': sorted(failed),
              'expected_behavior': {'tools': scenario.expected_tools, 'forbidden_tools': scenario.forbidden_tools,
                                    'belief_updates': scenario.expected_belief_updates,
                                    'response_requirements': scenario.expected_response_requirements},
              'result': result, 'error': outcome.error, 'human_review': 'not_reviewed',
              'artifacts': {name: str(output / f'{prefix}_{suffix}') for name, suffix in
                            (('run', 'run.json'), ('result', 'result.json'), ('trace', 'trace.jsonl'), ('review', 'review.json'))}}
    if outcome.run:
        run = outcome.run
        response = next(e.payload for e in run.events if e.event_type == 'agent_response')
        record.update(question=run.user_query, state_before=[b.to_dict() for b in run.initial_beliefs],
                      environment_before=run.initial_environment_state, state_after=[b.to_dict() for b in run.final_beliefs],
                      tools=[{'event_type': e.event_type, **e.payload} for e in run.events
                             if e.event_type in {'tool_call', 'tool_result'}], public_answer=response)
    else:
        record['artifacts'] = {'error': str(output / f'{prefix}_error.json'),
                               'trace': str(output / f'{prefix}_trace.jsonl')}
    return record


def contract_probe(output):
    scenario = load_scenario('S07')
    sensor = AbstentionSensorReference('S07', scenario.initial_environment_state)
    # Deliberately malformed public payload; never recover as unknown.
    sensor.read_temperature = lambda: {'sensor': 'temperature', 'value': 22}
    outcome = run_midproject('S07', 'malformed_probe', sensor_backend=sensor, output_dir=output)
    return {'scenario_id': 'S07', 'case': 'malformed_probe', 'expected_status': 'CONTRACT ERROR',
            'expected_category': 'malformed_payload', 'status': outcome.status, 'error': outcome.error,
            'expectation_met': outcome.status == 'CONTRACT ERROR' and outcome.error.get('error_category') == 'malformed_payload',
            'artifacts': {'error': str(output / 'S07_malformed_probe_error.json'),
                          'trace': str(output / 'S07_malformed_probe_trace.jsonl')}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('all', *SCENARIOS), default='all')
    parser.add_argument('--backend', choices=('reference',), default='reference')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'evaluation/logs/role4/midproject')
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    ids = SCENARIOS if args.scenario == 'all' else (args.scenario,)
    print('I, Agent | Five-case mid-project evaluation | reference | deterministic_reference')
    print('Scope: reference three-layer evaluation. Human semantic review: pending.')
    cases, review = [], []
    for scenario_id in ids:
        for kind in ('valid', 'injected_fault'):
            outcome = run_midproject(scenario_id, kind, injected_fault=kind == 'injected_fault', output_dir=output)
            record = case_record(scenario_id, kind, outcome, output)
            cases.append(record)
            print(f"{scenario_id} {kind}: {outcome.status} | expected {record['expected_status']} | "
                  + ('confirmed' if record['expectation_met'] else 'UNEXPECTED'))
            if record['failed_checks']:
                print('  Detected: ' + ', '.join(record['failed_checks']))
            if kind == 'valid' and outcome.run:
                worksheet = review_worksheet(outcome.run)
                worksheet['question'] = outcome.run.user_query
                worksheet['supporting_evidence'] = [item for e in outcome.run.events if e.event_type == 'tool_result'
                                                  for item in e.payload.get('evidence', [])]
                review.append(worksheet)
    probes = [contract_probe(output)] if 'S07' in ids else []
    for probe in probes:
        print(f"S07 malformed probe: {probe['status']} / {(probe['error'] or {}).get('error_category')} | "
              + ('confirmed' if probe['expectation_met'] else 'UNEXPECTED'))
    dependencies = dependency_status()
    print('Teammate discovery blockers (separate from this build): ' + ', '.join(dependencies['collection_blockers']))
    print('Missing official inputs: ' + ', '.join(dependencies['missing_inputs']))
    print(CLIENT_STATUS)
    verified = all(c['expectation_met'] for c in cases + probes)
    summary = {'phase': 'C', 'selection': args.scenario, 'backend_type': 'reference',
               'model_execution_mode': 'deterministic_reference', 'integration_scope': SCOPE,
               'teammate_modules_integrated': False, 'hosted_reliability_measured': False,
               'human_review': 'not_reviewed', 'cases': cases, 'contract_probes': probes,
               'all_expectations_met': verified, 'dependencies': dependencies,
               'readiness': {'five_case_reference_evaluation': verified and args.scenario == 'all',
                             'real_teammate_integration': False, 'full_test_discovery': False,
                             'human_prose_review': False, 'peer_review': False, 'merge_to_main': False, 'release_tag': False}}
    write_json(output / 'build_summary.json', summary)
    write_json(output / 'human_review_packet.json', {'status': 'not_reviewed', 'reviewer': None,
               'selection': args.scenario, 'responses': review, 'automatic_review_is_not_human_approval': True})
    lines = ['# Five-case reference result matrix', '',
             'Fault failures demonstrate evaluator detection; they are not agent reliability measurements.', '',
             '| Scenario | Valid | Injected fault | Expected outcomes met |', '|---|---|---|---|']
    for scenario_id in ids:
        pair = [c for c in cases if c['scenario_id'] == scenario_id]
        lines.append(f"| {scenario_id} | {pair[0]['status']} | {pair[1]['status']} | {all(c['expectation_met'] for c in pair)} |")
    lines += ['', 'Backend: reference. Model: deterministic_reference. Human review: pending.', '',
              CLIENT_STATUS, '', 'See build_summary.json for questions, states, tools, answers, expectations and artifact paths.']
    (output / 'result_matrix.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Artifacts: {output}')
    return 0 if verified else 1


if __name__ == '__main__':
    raise SystemExit(main())
