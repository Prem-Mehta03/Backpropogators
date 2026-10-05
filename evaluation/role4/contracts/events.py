"""Boundary validation and shared evidence types, reusing the Phase 1 models."""
from copy import deepcopy
from dataclasses import dataclass, asdict, field, MISSING
from datetime import datetime, timezone
from evaluation.role4.models import BeliefState, SensorReading, AgentResponseEvent, require_fields, validate_json, validate_confidence, utc_now

class ContractError(ValueError):
    """Malformed layer data or a broken integration contract."""

class SensorUnavailable(ContractError):
    """The layer cannot supply the requested sensor."""

def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f'{label} must be a nonempty string')
    return value

def debug_payload(raw):
    """Retain JSON raw data without letting an invalid Python object break error logging."""
    try:
        validate_json(raw)
        return deepcopy(raw)
    except (ValueError, TypeError):
        return {'raw_type': type(raw).__name__, 'note': 'Raw payload is not JSON serializable'}

def references(value, label='evidence_refs', *, allow_empty=False):
    if not isinstance(value, list) or (not value and (not allow_empty)):
        raise ContractError(f"{label} must be a {('possibly empty' if allow_empty else 'nonempty')} list")
    for item in value:
        nonempty(item, label)
    if len(set(value)) != len(value):
        raise ContractError(f'Duplicate {label}')
    return list(value)

def utc_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError('timezone missing')
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError) as exc:
        raise ContractError(f'Invalid timezone-aware observation timestamp: {value!r}') from exc

def belief_from_payload(raw):
    try:
        data = raw.to_dict() if isinstance(raw, BeliefState) else deepcopy(raw)
        fields = set(BeliefState.__dataclass_fields__)
        require_fields(data, fields, 'belief')
        validate_json(data)
        normalized = {key: data[key] for key in fields}
        normalized['observed_at'] = utc_timestamp(normalized['observed_at'])
        belief = BeliefState(**normalized)
        if belief.perspective not in {'historical', 'user', 'agent_sensor'} and (not belief.perspective.startswith('agent_sensor:')):
            raise ValueError(f'Unsupported perspective: {belief.perspective}')
        if belief.perspective == 'agent_sensor:':
            raise ValueError('Sensor perspective suffix must be nonempty')
        return belief
    except (ValueError, TypeError) as exc:
        raise ContractError(f'Invalid belief payload: {exc}') from exc

@dataclass
class SensorObservation:
    reading: SensorReading
    unit: str | None
    environment_revision: int

    @property
    def evidence_id(self):
        return self.reading.reading_id

    def to_dict(self):
        return {**self.reading.to_dict(), 'unit': self.unit, 'environment_revision': self.environment_revision}

def sensor_from_payload(raw, expected_sensor=None):
    try:
        data = raw.to_dict() if isinstance(raw, SensorObservation) else deepcopy(raw)
        fields = set(SensorReading.__dataclass_fields__)
        require_fields(data, fields | {'unit', 'environment_revision'}, 'sensor')
        validate_json(data)
        normalized = {key: data[key] for key in fields}
        normalized['observed_at'] = utc_timestamp(normalized['observed_at'])
        reading = SensorReading(**normalized)
        revision = data['environment_revision']
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError('environment_revision must be a positive integer')
        unit = data['unit']
        if unit is not None:
            nonempty(unit, 'unit')
        if 'distance_cm' in reading.details:
            distance = reading.details['distance_cm']
            if unit != 'cm' or isinstance(distance, bool) or (not isinstance(distance, (int, float))) or (distance < 0):
                raise ValueError("distance_cm requires a nonnegative number and unit 'cm'")
        if expected_sensor is not None and reading.sensor != expected_sensor:
            raise ValueError(f'Expected sensor {expected_sensor}, got {reading.sensor}')
        return SensorObservation(reading, unit, revision)
    except (ValueError, TypeError) as exc:
        raise ContractError(f'Invalid sensor payload: {exc}') from exc

@dataclass
class Evidence:
    evidence_id: str
    category: str
    data: dict

    @classmethod
    def from_payload(cls, raw):
        try:
            require_fields(raw, {'evidence_id', 'category', 'data'}, 'evidence')
            nonempty(raw['evidence_id'], 'evidence_id')
            nonempty(raw['category'], 'evidence category')
            if not isinstance(raw['data'], dict) or not raw['data']:
                raise ValueError('evidence data must be a nonempty object')
            validate_json(raw)
            return cls(raw['evidence_id'], raw['category'], deepcopy(raw['data']))
        except (ValueError, TypeError) as exc:
            raise ContractError(f'Invalid evidence: {exc}') from exc

    def to_dict(self):
        return asdict(self)

@dataclass
class ResponseMetadata:
    text: str
    evidence_refs: list[str]
    claims: dict
    acknowledge_conflict: bool
    acknowledge_uncertainty: bool
    acknowledge_missing: bool
    claim_support: list[dict] = field(default_factory=list)
    public_reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, raw):
        try:
            data = asdict(raw) if isinstance(raw, cls) else deepcopy(raw)
            required = {key for key, item in cls.__dataclass_fields__.items() if item.default is MISSING and item.default_factory is MISSING}
            require_fields(data, required, 'response')
            payload = {key: data[key] for key in cls.__dataclass_fields__ if key in data}
            AgentResponseEvent(utc_now(), 'agent_response', 'validation', payload)
            references(payload['evidence_refs'], allow_empty=True)
            support = payload.get('claim_support', [])
            if not isinstance(support, list):
                raise ValueError('claim_support must be a list')
            for item in support:
                require_fields(item, {'claim_key', 'value', 'evidence_id', 'perspective', 'source', 'confidence'}, 'claim support')
                for key in ('claim_key', 'evidence_id', 'perspective'):
                    nonempty(item[key], key)
                if item['source'] is not None:
                    nonempty(item['source'], 'claim source')
                validate_confidence(item['confidence'])
            reasons = payload.get('public_reasons', [])
            if not isinstance(reasons, list) or any((not isinstance(x, str) or not x.strip() for x in reasons)):
                raise ValueError('public_reasons must be a string list')
            return cls(**payload)
        except (ValueError, TypeError) as exc:
            raise ContractError(f'Invalid response payload: {exc}') from exc

    def to_dict(self):
        data = asdict(self)
        for optional in ('claim_support', 'public_reasons'):
            if not data[optional]:
                del data[optional]
        return data
