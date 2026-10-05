"""Configurable decision inputs and independent behavioral expectations."""

from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from evaluation.role4.contracts.events import ContractError
from evaluation.role4.models import validate_confidence

PHASE3_SCENARIOS = ("S02", "S03", "S04", "S05", "S08")


@dataclass(frozen=True)
class ExecutionPolicy:
    mode: str
    sensors: tuple[str, ...]
    minimum_sensor_confidence: float = 0.7
    maximum_observation_age_seconds: float = 300

    def __post_init__(self):
        validate_confidence(self.minimum_sensor_confidence)
        if isinstance(self.maximum_observation_age_seconds, bool) or not isinstance(self.maximum_observation_age_seconds, (float, int)) or self.maximum_observation_age_seconds < 0 or not math.isfinite(self.maximum_observation_age_seconds):
            raise ContractError("maximum_observation_age_seconds must be a finite nonnegative number")
        if self.mode not in {"current_observation", "perspectives", "confidence_conflict", "sensor_disagreement", "user_safety"}:
            raise ContractError(f"Unsupported execution policy mode: {self.mode}")
        allowed_sensors = {"lidar", "camera"}
        if not self.sensors or len(set(self.sensors)) != len(self.sensors) or any(s not in allowed_sensors for s in self.sensors):
            raise ContractError("Policy sensors must be unique supported sensor names")

    def to_dict(self):
        return {**asdict(self), "sensors": list(self.sensors)}


@dataclass(frozen=True)
class BehavioralPolicy:
    execution: ExecutionPolicy
    claim_perspectives: dict[str, str]

    def __post_init__(self):
        if not isinstance(self.execution, ExecutionPolicy):
            raise ContractError("Behavioral policy requires an ExecutionPolicy")
        if not isinstance(self.claim_perspectives, dict) or not self.claim_perspectives:
            raise ContractError("claim_perspectives must be a nonempty object")
        allowed = {"user", "historical", "agent_sensor", "agent_sensor:lidar", "agent_sensor:camera"}
        if any(not isinstance(key, str) or not key.strip() or value not in allowed for key, value in self.claim_perspectives.items()):
            raise ContractError("Each factual claim needs a nonempty name and a supported perspective")

    def to_dict(self):
        return {"execution": self.execution.to_dict(), "claim_perspectives": dict(self.claim_perspectives)}


def load_policies(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "tests/role4/phase3_policies.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw["scenarios"]) != set(PHASE3_SCENARIOS):
        raise ContractError("Phase 3 policies must cover exactly S02, S03, S04, S05 and S08")
    settings = raw["thresholds"]
    result = {}
    for scenario_id, data in raw["scenarios"].items():
        execution = ExecutionPolicy(data["mode"], tuple(data["sensors"]), **settings)
        if not isinstance(data["claim_perspectives"], dict) or not data["claim_perspectives"]:
            raise ContractError("claim_perspectives must be a nonempty object")
        result[scenario_id] = BehavioralPolicy(execution, data["claim_perspectives"])
    return result
