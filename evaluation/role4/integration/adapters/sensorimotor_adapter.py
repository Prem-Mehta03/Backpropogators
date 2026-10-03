"""Validate sensor dictionaries and preserve public raw returns for debugging."""
from copy import deepcopy
from evaluation.role4.contracts.events import ContractError, sensor_from_payload, nonempty, utc_timestamp
from evaluation.role4.models import SensorReading, require_fields, validate_json

class SensorimotorAdapter:

    def __init__(self, backend):
        self.backend = backend
        self.last_raw = None

    def reset(self, scenario_id):
        self.backend.reset(nonempty(scenario_id, 'scenario_id'))
        self.last_raw = None

    def get_environment_revision(self):
        revision = self.backend.get_environment_revision()
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ContractError('Environment revision must be a positive integer')
        return revision

    def get_environment_state(self):
        raw = deepcopy(self.backend.get_environment_state())
        try:
            require_fields(raw, {'fixture_time', 'revision', 'readings'}, 'environment state')
            validate_json(raw)
            utc_timestamp(raw['fixture_time'])
            if not isinstance(raw['readings'], list):
                raise ValueError('Environment readings must be a list')
            for reading in raw['readings']:
                fields = set(SensorReading.__dataclass_fields__)
                require_fields(reading, fields, 'environment sensor reading')
                SensorReading(**{key: reading[key] for key in fields})
            if isinstance(raw['revision'], bool) or not isinstance(raw['revision'], int) or raw['revision'] != self.get_environment_revision():
                raise ValueError('Environment snapshot revision disagrees with current revision')
        except (ValueError, TypeError) as exc:
            raise ContractError(f'Invalid environment state: {exc}') from exc
        self.last_raw = deepcopy(raw)
        return raw

    def _read(self, sensor):
        raw = getattr(self.backend, f'read_{sensor}')()
        self.last_raw = deepcopy(raw)
        observation = sensor_from_payload(raw, expected_sensor=sensor)
        if observation.environment_revision != self.get_environment_revision():
            raise ContractError('Sensor reading revision differs from the current environment revision')
        return observation

    def read_lidar(self):
        return self._read('lidar')

    def read_camera(self):
        return self._read('camera')

    def read_temperature(self):
        return self._read('temperature')
