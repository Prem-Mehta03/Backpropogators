"""Small, JSON-serializable contracts for later integration with all three layers."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def require_fields(data: dict, fields: set[str], label: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    missing = fields - data.keys()
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(sorted(missing))}")


def validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timezone-aware timestamp: {value!r}") from exc


def validate_confidence(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
        raise ValueError("confidence must be a number between 0 and 1")


def validate_json(value: Any) -> None:
    # Reject Python-only values, non-string dictionary keys, NaN, and infinity.
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            validate_json(item)
    elif isinstance(value, list):
        for item in value:
            validate_json(item)
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise ValueError(f"Unsupported JSON value: {type(value).__name__}")
    json.dumps(value, allow_nan=False)


@dataclass
class BeliefState:
    belief_id: str
    subject: str
    predicate: str
    value: Any
    perspective: str
    source: str | None
    confidence: float
    observed_at: str

    def __post_init__(self) -> None:
        for key in ("belief_id", "subject", "predicate", "perspective"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise ValueError(f"belief {key} must be a nonempty string")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ValueError("source must be a nonempty string or null")
        validate_confidence(self.confidence)
        validate_timestamp(self.observed_at)
        validate_json(self.value)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SensorReading:
    reading_id: str
    sensor: str
    subject: str
    predicate: str
    value: Any
    confidence: float
    observed_at: str
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key in ("reading_id", "sensor", "subject", "predicate"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise ValueError(f"sensor {key} must be a nonempty string")
        validate_confidence(self.confidence)
        validate_timestamp(self.observed_at)
        validate_json(self.value)
        if not isinstance(self.details, dict):
            raise ValueError("sensor details must be an object")
        validate_json(self.details)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScenarioSpecification:
    scenario_id: str
    name: str
    description: str
    initial_beliefs: list[BeliefState]
    initial_environment_state: dict
    user_query: str
    expected_tools: list[str]
    expected_belief_updates: list[dict]
    expected_response_requirements: dict
    pass_criteria: list[str]
    failure_conditions: list[str]
    tags: list[str]
    preserved_belief_ids: list[str]
    forbidden_tools: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "ScenarioSpecification":
        fields = set(cls.__dataclass_fields__)
        require_fields(data, fields, "scenario")
        if data.keys() - fields:
            raise ValueError(f"Unknown scenario fields: {sorted(data.keys() - fields)}")
        for key in ("scenario_id", "name", "description", "user_query"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise ValueError(f"scenario {key} must be a nonempty string")
        for key in ("expected_tools", "pass_criteria", "failure_conditions", "tags",
                    "preserved_belief_ids", "forbidden_tools"):
            if not isinstance(data[key], list) or any(not isinstance(x, str) or not x.strip() for x in data[key]):
                raise ValueError(f"scenario {key} must be a list of nonempty strings")
        for key in ("expected_tools", "pass_criteria", "failure_conditions", "tags"):
            if not data[key]:
                raise ValueError(f"scenario {key} cannot be empty")
        if not isinstance(data["initial_beliefs"], list) or not isinstance(data["expected_belief_updates"], list):
            raise ValueError("beliefs and updates must be lists")
        beliefs = []
        for raw in data["initial_beliefs"]:
            require_fields(raw, set(BeliefState.__dataclass_fields__), "initial belief")
            beliefs.append(BeliefState(**raw))
        ids = [b.belief_id for b in beliefs]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate initial belief IDs")
        if not set(data["preserved_belief_ids"]) <= set(ids):
            raise ValueError("Preserved belief ID not found in initial beliefs")
        if set(data["expected_tools"]) & set(data["forbidden_tools"]):
            raise ValueError("A tool cannot be both required and forbidden")
        update_ids = []
        for update in data["expected_belief_updates"]:
            require_fields(update, {"operation", "belief_id", "expected", "evidence_categories"}, "expected update")
            if update["operation"] != "upsert":
                raise ValueError("Phase 1 supports only upsert updates")
            require_fields(update["expected"], {"subject", "predicate", "value", "perspective", "source", "confidence"}, "expected belief")
            BeliefState(belief_id=update["belief_id"], observed_at="2026-01-01T00:00:00+00:00", **update["expected"])
            if not isinstance(update["evidence_categories"], list) or not update["evidence_categories"] or any(not isinstance(x, str) or not x for x in update["evidence_categories"]):
                raise ValueError("update evidence_categories must be a nonempty string list")
            update_ids.append(update["belief_id"])
        if len(set(update_ids)) != len(update_ids):
            raise ValueError("Duplicate expected update IDs")
        if set(update_ids) & set(data["preserved_belief_ids"]):
            raise ValueError("A belief cannot be both updated and preserved")
        if not isinstance(data["initial_environment_state"], dict):
            raise ValueError("initial_environment_state must be an object")
        environment = data["initial_environment_state"]
        require_fields(environment, {"fixture_time", "revision", "readings"}, "environment")
        validate_timestamp(environment["fixture_time"])
        if isinstance(environment["revision"], bool) or not isinstance(environment["revision"], int) or environment["revision"] < 1:
            raise ValueError("environment revision must be a positive integer")
        if not isinstance(environment["readings"], list):
            raise ValueError("environment readings must be a list")
        for reading in environment["readings"]:
            require_fields(reading, set(SensorReading.__dataclass_fields__), "sensor reading")
            SensorReading(**reading)
        if "change_during_reasoning" in environment:
            change = environment["change_during_reasoning"]
            require_fields(change, {"trigger", "next_revision", "reading"}, "environment change")
            if not isinstance(change["next_revision"], int) or change["next_revision"] <= environment["revision"]:
                raise ValueError("environment change must advance the revision")
            SensorReading(**change["reading"])
        req = data["expected_response_requirements"]
        require_fields(req, {"evidence_categories", "acknowledge_missing", "acknowledge_uncertainty", "acknowledge_conflict", "claims"}, "response requirements")
        if not isinstance(req["evidence_categories"], list) or not req["evidence_categories"] or any(not isinstance(x, str) or not x for x in req["evidence_categories"]):
            raise ValueError("response evidence_categories must be a nonempty string list")
        for key in ("acknowledge_missing", "acknowledge_uncertainty", "acknowledge_conflict"):
            if not isinstance(req[key], bool):
                raise ValueError(f"{key} must be boolean")
        if not isinstance(req["claims"], dict) or not req["claims"]:
            raise ValueError("response claims must be a nonempty object")
        validate_json(data)
        return cls(**{**data, "initial_beliefs": beliefs})

    def to_dict(self) -> dict:
        return asdict(self)


def load_scenarios(path: str | Path) -> list[ScenarioSpecification]:
    with Path(path).open(encoding="utf-8") as stream:
        raw = json.load(stream)
    if not isinstance(raw, list) or not raw:
        raise ValueError("Scenario registry must be a nonempty list")
    scenarios = [ScenarioSpecification.from_dict(item) for item in raw]
    ids = [s.scenario_id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate scenario IDs")
    return scenarios


@dataclass
class Event:
    timestamp: str
    event_type: str
    scenario_id: str
    payload: dict

    def __post_init__(self) -> None:
        validate_timestamp(self.timestamp)
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("Event scenario_id must be a nonempty string")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("Event type must be a nonempty string")
        if not isinstance(self.payload, dict):
            raise ValueError("Event payload must be an object")
        validate_json(self.payload)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolCallEvent(Event):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_type != "tool_call":
            raise ValueError("ToolCallEvent requires tool_call event type")
        require_fields(self.payload, {"call_id", "tool_name", "arguments"}, "tool call")
        if not isinstance(self.payload["arguments"], dict):
            raise ValueError("tool arguments must be an object")
        for key in ("call_id", "tool_name"):
            if not isinstance(self.payload[key], str) or not self.payload[key]:
                raise ValueError(f"tool {key} must be a nonempty string")


@dataclass
class BeliefUpdateEvent(Event):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_type != "belief_update":
            raise ValueError("BeliefUpdateEvent requires belief_update event type")
        require_fields(self.payload, {"operation", "before", "after", "evidence_refs"}, "belief update")
        if self.payload["operation"] != "upsert":
            raise ValueError("Phase 1 supports only upsert updates")
        BeliefState(**self.payload["after"])
        if self.payload["before"] is not None:
            BeliefState(**self.payload["before"])
        if not isinstance(self.payload["evidence_refs"], list) or any(not isinstance(x, str) for x in self.payload["evidence_refs"]):
            raise ValueError("update evidence_refs must be a string list")


@dataclass
class AgentResponseEvent(Event):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_type != "agent_response":
            raise ValueError("AgentResponseEvent requires agent_response event type")
        require_fields(self.payload, {"text", "evidence_refs", "claims", "acknowledge_missing", "acknowledge_uncertainty", "acknowledge_conflict"}, "agent response")
        if not isinstance(self.payload["text"], str) or not self.payload["text"].strip():
            raise ValueError("response text must be nonempty")
        if not isinstance(self.payload["claims"], dict):
            raise ValueError("response claims must be an object")
        if not isinstance(self.payload["evidence_refs"], list) or any(not isinstance(x, str) for x in self.payload["evidence_refs"]):
            raise ValueError("response evidence_refs must be a string list")
        for key in ("acknowledge_missing", "acknowledge_uncertainty", "acknowledge_conflict"):
            if not isinstance(self.payload[key], bool):
                raise ValueError(f"response {key} must be boolean")


def event_from_dict(raw: dict) -> Event:
    require_fields(raw, {"timestamp", "event_type", "scenario_id", "payload"}, "event")
    event_class = {"tool_call": ToolCallEvent, "belief_update": BeliefUpdateEvent,
                   "agent_response": AgentResponseEvent}.get(raw["event_type"], Event)
    return event_class(**raw)


@dataclass
class EvaluationResult:
    scenario_id: str
    run_id: str
    passed: bool
    checks: list[dict]
    failure_reasons: list[str]
    evaluated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestRunRecord:
    scenario_id: str
    run_id: str
    initial_beliefs: list[BeliefState]
    initial_environment_state: dict
    user_query: str
    events: list[Event]
    final_beliefs: list[BeliefState]
    result: EvaluationResult | None = None
    integration_metadata: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.integration_metadata is None:
            del data["integration_metadata"]
        return data

    @classmethod
    def from_dict(cls, raw: dict) -> "TestRunRecord":
        require_fields(raw, set(cls.__dataclass_fields__) - {"integration_metadata"}, "test run")
        return cls(**{**raw,
                      "initial_beliefs": [BeliefState(**b) for b in raw["initial_beliefs"]],
                      "final_beliefs": [BeliefState(**b) for b in raw["final_beliefs"]],
                      "events": [event_from_dict(e) for e in raw["events"]],
                      "result": EvaluationResult(**raw["result"]) if raw["result"] else None})
