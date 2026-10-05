"""Shared S01 and Phase 3 execution; public backends can replace the references."""
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
import re
from evaluation.role4.contracts.events import ContractError
from evaluation.role4.contracts.procedural import QueryContext
from evaluation.role4.evaluator import evaluate
from evaluation.role4.logger import EventLogger, write_json
from evaluation.role4.models import ScenarioSpecification, TestRunRecord, load_scenarios, utc_now
from evaluation.role4.integration.adapters.declarative_adapter import DeclarativeAdapter
from evaluation.role4.integration.adapters.procedural_adapter import ProceduralAdapter
from evaluation.role4.integration.adapters.sensorimotor_adapter import SensorimotorAdapter
from evaluation.role4.integration.trace_recorder import TraceRecorder, ToolDispatcher, ObservedBackend
ROOT = Path(__file__).resolve().parents[3]

@dataclass
class IntegrationOutcome:
    status: str
    run: TestRunRecord | None
    error: dict | None

def load_s01():
    return load_scenario('S01')

def load_scenario(scenario_id):
    for scenario in load_scenarios(ROOT / 'tests/role4/scenarios.json'):
        if scenario.scenario_id == scenario_id:
            return scenario
    raise ContractError(f'Unknown scenario ID: {scenario_id}')

def reference_backends(scenario, *, skip_lidar=False, malformed_lidar=False):
    from evaluation.role4.reference_layers.declarative_reference import DeclarativeReference
    from evaluation.role4.reference_layers.procedural_reference import ProceduralReference
    from evaluation.role4.reference_layers.sensorimotor_reference import SensorimotorReference
    return (DeclarativeReference(scenario.scenario_id, scenario.initial_beliefs), ProceduralReference(skip_lidar=skip_lidar), SensorimotorReference(scenario.scenario_id, scenario.initial_environment_state, malformed_lidar=malformed_lidar))

def run_s01(case_name, memory_backend, procedural_backend, sensor_backend, *, output_dir=None, layer_source='reference_layers', max_steps=8):
    return _execute(load_s01(), case_name, memory_backend, procedural_backend, sensor_backend, output_dir=output_dir, layer_source=layer_source, max_steps=max_steps)

def _execute(scenario, case_name, memory_backend, procedural_backend, sensor_backend, *, output_dir=None, layer_source='reference_layers', max_steps=8, behavioral_policy=None, metadata=None):
    if not re.fullmatch('[A-Za-z0-9_-]+', case_name):
        raise ContractError('case_name must be a safe filename identifier')
    run_id = f'{scenario.scenario_id}_{case_name}'
    output = Path(output_dir) if output_dir is not None else ROOT / 'evaluation/logs/role4/phase2'
    abstention = getattr(behavioral_policy, 'kind', None) == 'abstention'
    recorder = TraceRecorder(scenario.scenario_id, backend_type=metadata['backend_type'] if metadata else None, abstention=abstention)
    if metadata:
        memory_backend = ObservedBackend(memory_backend, 'declarative', recorder)
        procedural_backend = ObservedBackend(procedural_backend, 'procedural', recorder)
        sensor_backend = ObservedBackend(sensor_backend, 'sensorimotor', recorder)
        recorder.emit('scenario_start', {'run_id': run_id, 'name': scenario.name, 'execution': 'integrated'})
    memory, procedural, sensors = (DeclarativeAdapter(memory_backend), ProceduralAdapter(procedural_backend), SensorimotorAdapter(sensor_backend))
    try:
        memory.reset(scenario.scenario_id)
        sensors.reset(scenario.scenario_id)
        procedural.reset(scenario.scenario_id)
        initial = memory.get_belief_snapshot()
        environment = sensors.get_environment_state()
        if metadata:
            recorder.emit('beliefs_before', {'beliefs': [b.to_dict() for b in initial]})
            recorder.emit('environment_before', {'state': environment})
            recorder.emit('user_query', {'text': scenario.user_query})
        else:
            recorder.start(scenario, run_id, initial, environment)
        gateway = ToolDispatcher(memory, sensors, recorder, max_steps, scenario.forbidden_tools if metadata else (), abstention=abstention)
        target = ({'subject': behavioral_policy.subject, 'predicate': behavioral_policy.predicate} if abstention else
                  (scenario.initial_beliefs[0].to_dict() if scenario.initial_beliefs else scenario.initial_environment_state['readings'][0]))
        context = QueryContext(gateway, target['subject'], target['predicate'], max_steps)
        response = procedural.run_query(scenario.user_query, context)
        recorder.response(response, procedural.last_raw)
        recorder.finish()
        final = memory.get_belief_snapshot()
        run = TestRunRecord(scenario.scenario_id, run_id, initial, environment, scenario.user_query, list(recorder.events), final, integration_metadata=deepcopy(metadata))
        result = evaluate(scenario, run, behavioral_policy) if behavioral_policy else evaluate(scenario, run)
        run.result = result
        with EventLogger(output / f'{run_id}_trace.jsonl') as logger:
            logger.record_run(run, result)
        write_json(output / f'{run_id}_result.json', result.to_dict())
        write_json(output / f'{run_id}_run.json', run.to_dict())
        if metadata:
            from evaluation.role4.response_review import review_worksheet
            write_json(output / f'{run_id}_review.json', review_worksheet(run))
        return IntegrationOutcome('PASS' if result.passed else 'FAIL', run, None)
    except ContractError as exc:
        error = {'timestamp': utc_now(), 'scenario_id': scenario.scenario_id, 'run_id': run_id, 'status': 'CONTRACT ERROR', 'layer_source': layer_source, 'error_type': type(exc).__name__, 'message': str(exc), 'evaluated': False}
        errors = [e.payload for e in recorder.events if e.event_type == 'tool_error']
        error['error_category'] = errors[-1]['error_category'] if errors else 'contract_error'
        if metadata:
            error['integration_metadata'] = deepcopy(metadata)
        recorder.emit('contract_error', error)
        with EventLogger(output / f'{run_id}_trace.jsonl') as logger:
            for event in recorder.events:
                logger.record(event)
        write_json(output / f'{run_id}_error.json', error)
        return IntegrationOutcome('CONTRACT ERROR', None, error)
    except Exception as exc:
        # Phase C records unexpected execution failures, without converting them to abstention.
        if not metadata or metadata.get('phase') != 'C':
            raise
        error = {'timestamp': utc_now(), 'scenario_id': scenario.scenario_id, 'run_id': run_id,
                 'status': 'EXECUTION ERROR', 'error_category': 'execution_error',
                 'layer_source': layer_source, 'error_type': type(exc).__name__, 'message': str(exc),
                 'evaluated': False, 'integration_metadata': deepcopy(metadata)}
        recorder.emit('execution_error', error)
        with EventLogger(output / f'{run_id}_trace.jsonl') as logger:
            for event in recorder.events:
                logger.record(event)
        write_json(output / f'{run_id}_error.json', error)
        return IntegrationOutcome('EXECUTION ERROR', None, error)

def run_scenario(scenario_id, case_name='valid', *, initial_beliefs=None, initial_environment_state=None, user_query=None, execution_policy=None, expected_behavioral_policy=None, output_dir=None, backend_type='reference', layer_types=None, memory_backend=None, procedural_backend=None, sensor_backend=None, injected_fault=None, max_steps=8, build_scope=None):
    """Reusable Phase 3 path. Reference/real/mixed labels describe explicitly supplied backends."""
    from evaluation.role4.policies import PHASE3_SCENARIOS, load_policies
    from evaluation.role4.reference_layers.declarative_reference import DeclarativeReference
    from evaluation.role4.reference_layers.sensorimotor_reference import SensorimotorReference
    from evaluation.role4.reference_layers.conflict_procedural_reference import ConflictProceduralReference
    from evaluation.role4.reference_layers.procedural_reference import ProceduralReference
    if scenario_id not in PHASE3_SCENARIOS:
        raise ContractError('Phase 3 supports S02, S03, S04, S05 and S08 only')
    scenario = load_scenario(scenario_id)
    raw = scenario.to_dict()
    if initial_beliefs is not None:
        raw['initial_beliefs'] = [b.to_dict() if hasattr(b, 'to_dict') else deepcopy(b) for b in initial_beliefs]
    if initial_environment_state is not None:
        raw['initial_environment_state'] = deepcopy(initial_environment_state)
    if user_query is not None:
        raw['user_query'] = user_query
    scenario = ScenarioSpecification.from_dict(raw)
    expected = expected_behavioral_policy or load_policies()[scenario_id]
    decision = execution_policy or expected.execution
    if backend_type not in {'reference', 'real', 'mixed'}:
        raise ContractError('backend_type must be reference, real or mixed')
    supplied = {'declarative': memory_backend, 'procedural': procedural_backend, 'sensorimotor': sensor_backend}
    labels = layer_types or {key: backend_type for key in supplied}
    if set(labels) != set(supplied) or any((value not in {'reference', 'real'} for value in labels.values())):
        raise ContractError('layer_types must label each of the three layers reference or real')
    actual_type = 'mixed' if len(set(labels.values())) > 1 else next(iter(labels.values()))
    if actual_type != backend_type:
        raise ContractError('Backend label disagrees with layer_types')
    reference_classes = (DeclarativeReference, SensorimotorReference, ConflictProceduralReference, ProceduralReference)
    for key, backend in supplied.items():
        if labels[key] == 'real' and (backend is None or isinstance(backend, reference_classes)):
            raise ContractError(f'A real {key} backend must be supplied; references cannot be labelled real')
        if labels[key] == 'reference' and backend is not None and (not isinstance(backend, reference_classes)):
            raise ContractError(f'A non-reference {key} backend must be labelled real')
    if injected_fault is not None and procedural_backend is not None:
        raise ContractError('Injected faults require the runner-created procedural reference')
    memory_backend = memory_backend or DeclarativeReference(scenario_id, scenario.initial_beliefs)
    sensor_class = SensorimotorReference
    procedural_class = ConflictProceduralReference
    sensor_backend = sensor_backend or sensor_class(scenario_id, scenario.initial_environment_state)
    procedural_backend = procedural_backend or procedural_class(decision, scenario.initial_environment_state['fixture_time'], fault=injected_fault)
    metadata = {
        'backend_type': backend_type,
        'layer_types': dict(labels),
        'model_execution_mode': 'deterministic_reference' if labels['procedural'] == 'reference' else 'unreported',
        'injected_fault': injected_fault,
        'execution_policy': decision.to_dict(),
        'expected_behavioral_policy': expected.to_dict(),
        'human_review': 'not_reviewed',
    }
    if build_scope == 'five_case_reference_evaluation':
        metadata.update(phase='C', integration_scope=build_scope, teammate_modules_integrated=False)
    elif build_scope is not None:
        raise ContractError('Unsupported build scope')
    output = Path(output_dir) if output_dir else ROOT / 'evaluation/logs/role4/phase3'
    return _execute(scenario, case_name, memory_backend, procedural_backend, sensor_backend, output_dir=output, layer_source=backend_type, max_steps=max_steps, behavioral_policy=expected, metadata=metadata)
