"""Record calls at live adapter boundaries, never reconstruct a trace afterwards."""
from copy import deepcopy
from evaluation.role4.contracts.events import (
    ContractError, SensorUnavailable, Evidence, ResponseMetadata, belief_from_payload,
    references, nonempty, debug_payload,
)
from evaluation.role4.models import Event, ToolCallEvent, BeliefUpdateEvent, AgentResponseEvent, utc_now

class TraceRecorder:

    def __init__(self, scenario_id, *, backend_type=None, abstention=False):
        self.scenario_id = scenario_id
        self.events = []
        self.pending = {}
        self.seen_calls = set()
        self.evidence = {}
        self.response_recorded = False
        self.backend_type = backend_type
        self.boundary_count = 0
        self.abstention = abstention

    def emit(self, kind, payload):
        if self.backend_type and kind not in {'scenario_start', 'beliefs_before', 'environment_before', 'user_query'}:
            payload = deepcopy(payload)
            payload['backend_type'] = self.backend_type
            if 'source_layer' not in payload:
                tool = payload.get('tool_name', '')
                if tool.startswith('read_') or tool == 'move_forward':
                    payload['source_layer'] = 'sensorimotor'
                elif tool in {'query_memory', 'update_belief'} or kind == 'belief_update':
                    payload['source_layer'] = 'declarative'
                else:
                    payload['source_layer'] = 'procedural'
            if kind == 'tool_call':
                payload['state'] = 'requested'
            elif kind == 'tool_result':
                payload.setdefault('state', 'success')
            elif kind in {'tool_error', 'contract_error'}:
                payload['state'] = 'error'
        cls = {'tool_call': ToolCallEvent, 'belief_update': BeliefUpdateEvent, 'agent_response': AgentResponseEvent}.get(kind, Event)
        event = cls(utc_now(), kind, self.scenario_id, deepcopy(payload))
        self.events.append(event)

    def start(self, scenario, run_id, beliefs, environment):
        self.emit('scenario_start', {'run_id': run_id, 'name': scenario.name, 'execution': 'integrated'})
        self.emit('beliefs_before', {'beliefs': [b.to_dict() for b in beliefs]})
        self.emit('environment_before', {'state': environment})
        self.emit('user_query', {'text': scenario.user_query})

    def begin_tool(self, name, arguments, call_id=None):
        if self.response_recorded:
            raise ContractError('Cannot invoke a tool after the final response')
        call_id = call_id if call_id is not None else f'call_{len(self.seen_calls) + 1:03}'
        nonempty(call_id, 'tool call ID')
        if call_id in self.seen_calls:
            raise ContractError(f'Duplicate tool call ID: {call_id}')
        self.emit('tool_call', {'call_id': call_id, 'tool_name': name, 'arguments': arguments})
        self.seen_calls.add(call_id)
        self.pending[call_id] = name
        return call_id

    def tool_result(self, call_id, name, result):
        if self.pending.get(call_id) != name:
            raise ContractError(f'Unmatched tool result: {call_id} / {name}')
        if not isinstance(result, dict) or not isinstance(result.get('evidence'), list):
            raise ContractError('Tool result requires an evidence list (possibly empty)')
        if {'call_id', 'tool_name'} & result.keys():
            raise ContractError('Tool result data must not override its call ID or tool name')
        items = [Evidence.from_payload(item) for item in result['evidence']]
        ids = [item.evidence_id for item in items]
        if len(set(ids)) != len(ids) or set(ids) & self.evidence.keys():
            raise ContractError('Duplicate evidence IDs in tool returns')
        self.emit('tool_result', {'call_id': call_id, 'tool_name': name, **deepcopy(result)})
        self.evidence.update({item.evidence_id: item for item in items})
        del self.pending[call_id]

    def tool_error(self, call_id, name, error, raw=None):
        if self.pending.get(call_id) != name:
            raise ContractError('Unmatched tool error')
        self.emit('tool_error', {
            'call_id': call_id, 'tool_name': name,
            'error': str(error), 'raw': debug_payload(raw),
            'error_category': 'tool_unavailable' if isinstance(error, SensorUnavailable) else
                              ('malformed_payload' if name.startswith('read_') else 'contract_error'),
        })
        del self.pending[call_id]

    def require_evidence(self, refs):
        refs = references(refs, allow_empty=True)
        missing = set(refs) - self.evidence.keys()
        if missing:
            raise ContractError(f'Unknown evidence references: {sorted(missing)}')
        return refs

    def belief_update(self, call_id, receipt):
        self.require_evidence(receipt.evidence_refs)
        if call_id in self.pending or not any((e.event_type == 'tool_result' and e.payload['call_id'] == call_id and (e.payload['tool_name'] == 'update_belief') for e in self.events)):
            raise ContractError('Belief update must follow a completed update_belief call')
        self.emit('belief_update', {'call_id': call_id, 'operation': 'upsert', **receipt.to_dict()})

    def response(self, metadata, raw=None):
        if self.response_recorded or self.pending:
            raise ContractError('Final response must be unique and follow all tool returns')
        metadata = ResponseMetadata.from_payload(metadata)
        self.require_evidence(metadata.evidence_refs)
        payload = metadata.to_dict()
        if raw is not None:
            payload['raw'] = debug_payload(raw)
        self.emit('agent_response', payload)
        self.response_recorded = True

    def finish(self):
        if self.pending or not self.response_recorded:
            raise ContractError('Incomplete execution: missing tool return or final response')

class ToolDispatcher:
    """Only this gateway invokes the public adapters on behalf of the procedural layer."""

    def __init__(self, memory, sensors, recorder, max_steps=8, forbidden_tools=(), *, abstention=False):
        self.memory, self.sensors, self.recorder = (memory, sensors, recorder)
        self.max_steps = max_steps
        self.steps = 0
        self.forbidden_tools = set(forbidden_tools)
        self.abstention = abstention

    def call(self, name, arguments):
        if self.steps >= self.max_steps:
            raise ContractError(f'Maximum tool steps exceeded: {self.max_steps}')
        call_id = self.recorder.begin_tool(name, arguments)
        self.steps += 1
        receipt = None
        try:
            if name in self.forbidden_tools:
                result = {
                    'state': 'rejected', 'authorized': False, 'executed': False,
                    'reason': 'Action forbidden by scenario safety policy', 'evidence': [],
                }
            elif name == 'query_memory':
                beliefs = self.memory.get_beliefs(arguments['subject'], arguments['predicate'])
                result = {'beliefs': [b.to_dict() for b in beliefs], 'raw': deepcopy(self.memory.last_raw), 'evidence': [{'evidence_id': f'{call_id}:memory:{b.belief_id}', 'category': memory_category(b), 'data': b.to_dict()} for b in beliefs]}
                if self.abstention and not beliefs:
                    result.update(status='empty_result', evidence=[{
                        'evidence_id': f'{call_id}:memory_lookup', 'category': 'memory_lookup',
                        'data': {'subject': arguments['subject'], 'predicate': arguments['predicate'],
                                 'status': 'empty_result', 'found': False},
                    }])
            elif name in {'read_lidar', 'read_camera'} or (self.abstention and name == 'read_temperature'):
                try:
                    observation = getattr(self.sensors, name)()
                except SensorUnavailable as exc:
                    if not (self.abstention and name == 'read_temperature'):
                        raise
                    result = {'state': 'unavailable', 'status': 'unavailable', 'error_category': 'tool_unavailable',
                              'error_type': type(exc).__name__, 'message': str(exc), 'evidence': [{
                                  'evidence_id': f'{call_id}:sensor_availability', 'category': 'sensor_availability',
                                  'data': {'sensor': 'temperature', 'available': False, 'status': 'unavailable'},
                              }]}
                else:
                    result = {'observation': observation.to_dict(), 'raw': deepcopy(self.sensors.last_raw), 'evidence': [{'evidence_id': observation.evidence_id, 'category': observation.reading.sensor, 'data': observation.to_dict()}]}
            else:
                if name == 'update_belief':
                    refs = self.recorder.require_evidence(arguments['evidence_refs'])
                    receipt = self.memory.upsert_belief(belief_from_payload(arguments['belief']), refs)
                    result = {'belief': receipt.after.to_dict(), 'before': receipt.before.to_dict() if receipt.before else None, 'evidence_refs': receipt.evidence_refs, 'evidence': [], 'raw': deepcopy(self.memory.last_raw)}
                else:
                    raise ContractError(f'Unsupported tool: {name}')
            self.recorder.tool_result(call_id, name, result)
            if receipt:
                self.recorder.belief_update(call_id, receipt)
            return deepcopy(result)
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            error = exc if isinstance(exc, ContractError) else ContractError(f'Invalid {name} boundary: {exc}')
            if call_id in self.recorder.pending:
                raw = self.sensors.last_raw if name.startswith('read_') else self.memory.last_raw
                self.recorder.tool_error(call_id, name, error, deepcopy(raw))
            if error is exc:
                raise
            raise error from exc

def memory_category(belief):
    if belief.perspective == 'user':
        return 'user'
    if belief.source in {'stored_map', 'stored_record'}:
        return belief.source
    if belief.perspective == 'historical':
        return 'historical'
    return belief.source or 'unverified_memory'

class ObservedBackend:
    """Observe public backend calls, including reset/snapshot calls made inside adapters."""

    def __init__(self, backend, source_layer, recorder):
        self.backend, self.source_layer, self.recorder = (backend, source_layer, recorder)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise ContractError('Adapters must use public backend operations')
        operation = getattr(self.backend, name)
        if not callable(operation):
            raise ContractError(f'Backend operation is not callable: {name}')

        def call(*args, **kwargs):
            self.recorder.boundary_count += 1
            call_id = f'boundary_{self.recorder.boundary_count:03}'
            common = {'call_id': call_id, 'source_layer': self.source_layer, 'operation': name}
            self.recorder.emit('boundary_call', {**common, 'state': 'requested', 'request': {'args': public_data(list(args)), 'kwargs': public_data(kwargs)}})
            try:
                result = operation(*args, **kwargs)
            except Exception as exc:
                self.recorder.emit('boundary_result', {
                    **common, 'state': 'error', 'error': str(exc),
                    'error_type': type(exc).__name__,
                    'error_category': 'tool_unavailable' if isinstance(exc, SensorUnavailable) else 'execution_error',
                })
                raise
            self.recorder.emit('boundary_result', {**common, 'state': 'returned', 'response': public_data(result)})
            return result
        return call

def public_data(value):
    from evaluation.role4.contracts.procedural import QueryContext
    if isinstance(value, QueryContext):
        return {'subject': value.subject, 'predicate': value.predicate, 'max_steps': value.max_steps}
    if isinstance(value, list):
        return [public_data(item) for item in value]
    if isinstance(value, dict):
        return {key: public_data(item) for key, item in value.items()}
    if hasattr(value, 'to_dict'):
        return public_data(value.to_dict())
    return debug_payload(value)
