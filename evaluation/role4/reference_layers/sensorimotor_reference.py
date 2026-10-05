"""Deterministic sensor fixtures, without a simulator or movement implementation."""

from copy import deepcopy
from evaluation.role4.contracts.events import ContractError, SensorUnavailable


class SensorimotorReference:
    def __init__(self, scenario_id, environment, *, malformed_lidar=False):
        self.scenario_id = scenario_id
        self.initial = deepcopy(environment)
        self.malformed_lidar = malformed_lidar
        self.reset(scenario_id)

    def reset(self, scenario_id):
        if scenario_id != self.scenario_id:
            raise ContractError(f"Sensor reference supports only {self.scenario_id}")
        self._environment = deepcopy(self.initial)

    def get_environment_state(self):
        return deepcopy(self._environment)

    def get_environment_revision(self):
        return self._environment["revision"]

    def _read(self, name):
        for reading in self._environment["readings"]:
            if reading["sensor"] == name:
                return {**deepcopy(reading), "unit": "cm" if "distance_cm" in reading["details"] else None,
                        "environment_revision": self.get_environment_revision()}
        raise SensorUnavailable(f"Reference sensor unavailable: {name}")

    def read_lidar(self):
        payload = self._read("lidar")
        if self.malformed_lidar:
            del payload["confidence"]  # Intentional Case C fault, isolated at the raw boundary.
        return payload

    def read_camera(self):
        return self._read("camera")
