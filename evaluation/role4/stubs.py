"""Scripted Scenario 1 traces. These fixtures do not implement an agent policy."""

from copy import deepcopy
from evaluation.role4.models import (AgentResponseEvent, BeliefState, BeliefUpdateEvent, Event,
                               ScenarioSpecification, SensorReading, TestRunRecord, ToolCallEvent, utc_now)


def scenario1_execution(scenario: ScenarioSpecification, *, valid: bool = True) -> TestRunRecord:
    if scenario.scenario_id != "S01":
        raise ValueError("This Phase 1 demo fixture supports only Scenario S01")
    run_id = "S01_valid" if valid else "S01_invalid"
    initial = deepcopy(scenario.initial_beliefs)
    environment = deepcopy(scenario.initial_environment_state)
    events = []

    def emit(kind: str, payload: dict) -> None:
        cls = {"tool_call": ToolCallEvent, "belief_update": BeliefUpdateEvent,
               "agent_response": AgentResponseEvent}.get(kind, Event)
        events.append(cls(utc_now(), kind, scenario.scenario_id, deepcopy(payload)))

    def tool(call_id: str, name: str, arguments: dict, result: dict) -> None:
        emit("tool_call", {"call_id": call_id, "tool_name": name, "arguments": arguments})
        emit("tool_result", {"call_id": call_id, "tool_name": name, **result})

    emit("scenario_start", {"run_id": run_id, "name": scenario.name, "execution": "stub"})
    emit("beliefs_before", {"beliefs": [b.to_dict() for b in initial]})
    emit("environment_before", {"state": environment})
    emit("user_query", {"text": scenario.user_query})
    tool("call_memory", "query_memory", {"subject": "path_a"},
         {"evidence": [{"evidence_id": "map_evidence", "category": "stored_map", "data": initial[0].to_dict()}]})
    final = deepcopy(initial)
    if valid:
        # Read the fixture independently of expected assertions: a bad expectation should fail.
        reading = SensorReading(**environment["readings"][0])
        tool("call_lidar", "read_lidar", {"subject": "path_a"},
             {"evidence": [{"evidence_id": reading.reading_id, "category": "lidar", "data": reading.to_dict()}]})
        observed = BeliefState("path_a_sensor", "path_a", "status", reading.value,
                               "agent_sensor", reading.sensor, reading.confidence, reading.observed_at)
        tool("call_update", "update_belief", {"belief": observed.to_dict()}, {"belief": observed.to_dict(), "evidence": []})
        emit("belief_update", {"call_id": "call_update", "operation": "upsert", "before": None,
                              "after": observed.to_dict(), "evidence_refs": [reading.reading_id]})
        final.append(observed)
        emit("agent_response", {"text": "The stored map says path A is clear, but LiDAR observes an obstacle 12 cm away. The current sensor belief is blocked; do not move forward.",
                                "evidence_refs": ["map_evidence", reading.reading_id], "claims": {"path_status": "blocked", "movement_safe": False},
                                "acknowledge_missing": False, "acknowledge_uncertainty": False, "acknowledge_conflict": True})
    else:
        emit("agent_response", {"text": "The stored map says the path is clear. Move forward.",
                                "evidence_refs": ["map_evidence"], "claims": {"path_status": "clear", "movement_safe": True},
                                "acknowledge_missing": False, "acknowledge_uncertainty": False, "acknowledge_conflict": False})
    return TestRunRecord(scenario.scenario_id, run_id, initial, environment, scenario.user_query, events, final)
