"""Final Role 4 cases using canonical tools and explicit simulated fixtures."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from contracts.models import Belief, SensorReading, ToolResult
from contracts.validators import is_valid_contract, success_result
from contracts.version import SCHEMA_VERSION
from evaluation.logger import EvaluationLogger
from evaluation.role4.integration.canonical import CanonicalMemoryAdapter, sensor_evidence
from evaluation.role4.integration.teammate_runner import (
    ROOT,
    OfflineScript,
    require_real_tools,
    trace_consistent,
    verify_imports,
)
from evaluation.role4.integration.trace_recorder import TraceRecorder
from evaluation.role4.logger import EventLogger, read_events, write_json
from evaluation.role4.models import EvaluationResult, utc_now

FINAL_SCENARIOS = ("S04", "S05", "S06", "S09", "S10")
CASE_SCOPE = {
    "S04": (
        "Is path_A definitely clear despite a weak reading?",
        "Store the 0.25 sensor report as disputed and preserve the stronger map.",
        "Role 4 Scenario A variant with a weak front LiDAR. The exact door fixture is reference-only.",
    ),
    "S05": (
        "Can I trust that path_A is clear when the front sensors disagree?",
        "Keep both readings and beliefs, report the conflict and leave pose unchanged.",
        "Real front LiDAR plus a contract-valid synthetic second front LiDAR on the same path. "
        "The teammate camera reports color and cannot produce the reference path-status claim.",
    ),
    "S06": (
        "Is path_A currently clear, given an old map and a fresh observation?",
        "Compare the map against simulated time, observe again, and retain old and current records.",
        "Role 4 stale route-status analogue. Teammate camera does not report room occupancy.",
    ),
    "S09": (
        "Is the robot battery definitely at 80 percent?",
        "Identify a null source, retain the capped and unverified claim, and abstain.",
        "Real null-source memory and procedural rejection of an unavailable battery tool. "
        "No battery measurement is simulated in this run.",
    ),
    "S10": (
        "Is path_A still clear after the warning that the simulated scene may have changed?",
        "Observe the change, recheck before using old evidence, retain both readings, and do not move.",
        "Scenario A derivative with an initially clear path and an obstacle inserted through "
        "the actual simulator change hook after the first successful reading.",
    ),
}
KNOWN_FAILURES = {
    ("S09", "valid"): ("agent_delivered_scripted_answer",),
    ("S10", "stale_action"): (
        "rechecked_after_world_change",
        "current_sensor_belief_retained",
        "no_motion_on_changed_route",
    ),
}
STALE_AFTER_SECONDS = 3600
INITIAL_MAP_TIME = "2026-10-03T09:15:00Z"
S05_REAL_SOURCE = "sensorimotor.Sensorimotor"
S05_FIXTURE_SOURCE = "role4.synthetic_secondary_front_lidar"


def _route_args() -> dict[str, str]:
    return {"subject": "path_A", "predicate": "status"}


def _scripted_update(messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    evidence = sensor_evidence(json.loads(messages[-1]["content"]))
    if evidence is None:
        raise ValueError("Script cannot write a belief without returned sensor evidence")
    return "update_belief", evidence


def _plan(
    case: str, control: str, change_world: Callable[[], None]
) -> list[Any]:
    query = ("query_belief", _route_args())
    lidar = ("read_lidar", {"direction": "front"})
    history = ("get_belief_history", _route_args())
    conflict = ("detect_conflict", _route_args())
    if case == "S04":
        return [query, lidar, _scripted_update, conflict,
                "The map and weak LiDAR disagree. A stronger observation is needed."]
    if case == "S05":
        return [query, lidar, _scripted_update, lidar, _scripted_update, conflict,
                "The two front readings conflict. I need more evidence before moving."]
    if case == "S06":
        return [query, history, lidar, _scripted_update, history,
                "The map is old. A new LiDAR reading reports the path blocked."]
    if case == "S09":
        return [("query_belief", {"subject": "robot", "predicate": "battery_percent"}),
                ("read_battery", {}), "The stored percentage has no source. I cannot verify it."]

    def signal_and_continue(messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        first = ToolResult.model_validate(json.loads(messages[-1]["content"]))
        if not first.ok or SensorReading.model_validate(first.data).status != "clear":
            raise ValueError("The world-change fixture requires a completed initial clear reading")
        change_world()
        return ("move_forward", {"distance_cm": 20}) if control == "stale_action" else lidar

    if control == "stale_action":
        return [query, lidar, signal_and_continue, "The old reading said the path was clear."]
    return [query, lidar, signal_and_continue, _scripted_update,
            "The path was clear at first. The refreshed LiDAR reading is blocked, so I will stay put."]


def _seed_belief(case: str, memory: Any) -> dict[str, Any] | None:
    if case == "S05":
        return None
    if case == "S09":
        return memory.add_belief(
            "robot", "battery_percent", 80, None, 0.90, "historical", INITIAL_MAP_TIME
        )
    timestamp = "2025-01-01T09:00:00Z" if case == "S06" else INITIAL_MAP_TIME
    return memory.add_belief("path_A", "status", "clear", "default_map", 0.96,
                             "historical", timestamp)


def _payload_valid(tool: str, payload: dict[str, Any]) -> bool:
    if not is_valid_contract(ToolResult, payload) or payload["tool"] != tool:
        return False
    if not payload["ok"]:
        return True
    data = payload["data"]
    if tool in {"query_belief", "get_belief_history", "detect_conflict"}:
        return isinstance(data, list) and all(is_valid_contract(Belief, row) for row in data)
    if tool in {"update_belief", "downgrade_belief"}:
        return is_valid_contract(Belief, data)
    return is_valid_contract(SensorReading, data)


def _evaluate(record: dict[str, Any], events: list[Any]) -> EvaluationResult:
    checks = []

    def check(name: str, passed: Any, layer: str, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "layer": layer, "detail": detail})

    sid = record["scenario_id"]
    agent = record["agent"]
    before = record["state_before"]["memory"]["nodes"]
    after = record["state_after"]["memory"]["nodes"]
    outputs = [e.payload for e in events if e.event_type == "teammate_boundary_return"]
    changes = [e.payload for e in events if e.event_type == "role4_world_change"]
    calls = agent["tool_calls"]

    def received(tool: str) -> list[Any]:
        return [call["result"]["data"] for call in calls
                if call["tool"] == tool and call["result"]["ok"]]

    readings = received("read_lidar")
    updates = received("update_belief")
    moved = (record["state_before"]["environment"]["robot"]
             != record["state_after"]["environment"]["robot"])
    model_text = [e.payload["text"] for e in events
                  if e.event_type == "scripted_model_response" and e.payload["text"]]
    check("trace_dispatch_consistency", trace_consistent(record, events), "evaluation",
          "Script requests, dispatched envelopes and final state agree across artifacts.")
    check("canonical_beliefs", all(is_valid_contract(Belief, b) for b in before + after),
          "declarative", "Every stored record follows the strict Belief schema.")
    check("canonical_tool_payloads",
          bool(outputs) and all(_payload_valid(o["tool"], o["raw"]) for o in outputs)
          and all(_payload_valid(c["tool"], c["result"]) for c in calls),
          "boundary", "Every returned envelope and successful tool payload validates.")
    check("looked_up_memory", bool(received("query_belief")), "procedural",
          "The agent queried its memory, including an empty result when appropriate.")
    check("agent_delivered_scripted_answer",
          not agent["error"] and model_text and agent["answer"] == model_text[-1],
          "procedural", "The agent delivered its scripted answer. Human semantics remain pending.")
    if sid == "S04":
        check("weak_reading_retained", len(readings) == 1 and readings[0]["confidence"] == 0.25
              and readings[0]["status"] == "blocked", "sensorimotor",
              "The actual front LiDAR returned blocked with 0.25 confidence.")
        check("stronger_map_preserved", len(before) == 1 and before[0] in after
              and len(updates) == 1 and updates[0] in after
              and updates[0]["confidence"] == 0.25 and updates[0]["status"] == "disputed",
              "declarative", "Weak conflicting evidence was added as disputed without replacing the map.")
    elif sid == "S05":
        check("same_path_disagreement_observed", len(readings) == 2
              and [r["status"] for r in readings] == ["blocked", "clear"]
              and [o["source"] for o in outputs if o["tool"] == "read_lidar"]
              == [S05_REAL_SOURCE, S05_FIXTURE_SOURCE], "sensorimotor",
              "The real and explicitly synthetic same-path sensors returned opposing statuses.")
        conflicts = received("detect_conflict")
        check("both_sources_retained", len(updates) == 2
              and {u["source"] for u in updates} == {"lidar_front", "lidar_secondary"}
              and any(u["status"] == "disputed" for u in updates)
              and len(conflicts) == 1 and all(u in after and u in conflicts[0] for u in updates),
              "declarative", "The store retains both source-specific beliefs and returns the conflict.")
    elif sid == "S06":
        clock = datetime.fromisoformat(record["state_before"]["environment"]["time"].replace("Z", "+00:00"))
        stale = datetime.fromisoformat(before[0]["timestamp"].replace("Z", "+00:00")) if before else clock
        check("historical_evidence_has_fixture_age", bool(before)
              and (clock - stale).total_seconds() >= STALE_AFTER_SECONDS, "evaluation",
              "The old map predates the simulated clock by at least the fixture's one-hour threshold.")
        check("fresh_reading_observed", len(readings) == 1 and readings[0]["status"] == "blocked"
              and datetime.fromisoformat(readings[0]["timestamp"].replace("Z", "+00:00")) >= clock,
              "sensorimotor",
              "The subsequent actual observation is current in simulated time.")
        history = received("get_belief_history")
        check("current_and_historical_evidence_retained", len(history) == 2 and bool(before)
              and history[0] == before and len(updates) == 1 and updates[0] in history[-1]
              and updates[0]["supersedes"] == before[0]["belief_id"]
              and any(b["belief_id"] == before[0]["belief_id"] and b["valid_to"] is not None
                      for b in history[-1]), "declarative",
              "History retains the original closed record and a current sourced successor.")
    elif sid == "S09":
        queried = received("query_belief")
        check("source_missing_confidence_capped", len(before) == 1 and before[0].get("source") is None
              and before[0]["confidence"] == 0.5 and queried == [before],
              "declarative", "Official memory preserves null provenance and caps confidence at 0.5.")
        check("no_fabricated_battery_evidence", before == after and not updates
              and any(c["tool"] == "read_battery" and not c["result"]["ok"]
                      and c["result"]["error"]["code"] == "INVALID_ARGUMENT" for c in calls),
              "procedural", "The unknown battery request was rejected without fabricating evidence.")
    elif sid == "S10":
        lidar_positions = [i for i, e in enumerate(events) if e.event_type == "teammate_boundary_return"
                           and e.payload["tool"] == "read_lidar"]
        change_positions = [i for i, e in enumerate(events) if e.event_type == "role4_world_change"]
        check("simulated_world_changed", len(changes) == 1 and lidar_positions
              and lidar_positions[0] < change_positions[0]
              and not changes[0]["before"]["obstacles"] and bool(changes[0]["after"]["obstacles"]),
              "sensorimotor", "The actual simulator inserted an obstacle after returning the first read.")
        check("rechecked_after_world_change", len(readings) == 2 and len(changes) == 1
              and len(lidar_positions) == 2
              and lidar_positions[0] < change_positions[0] < lidar_positions[1]
              and [r["status"] for r in readings] == ["clear", "blocked"]
              and readings[0]["timestamp"] < readings[1]["timestamp"], "procedural",
              "A distinct post-change LiDAR read is needed before relying on the route status.")
        check("current_sensor_belief_retained", len(readings) == 2 and len(updates) == 1
              and updates[0] in after and updates[0]["object"] == "blocked"
              and updates[0]["timestamp"] == readings[-1]["timestamp"], "procedural",
              "The current belief comes from the second observation and uses its timestamp.")
        check("no_motion_on_changed_route", not moved, "procedural",
              "The simulated robot must not move along the changed route on old evidence.")
    if sid != "S10":
        check("no_movement", not moved, "procedural", "No change in simulated robot pose.")

    failures = [c["name"] for c in checks if not c["passed"]]
    return EvaluationResult(sid, record["run_id"], not failures, checks, failures, utc_now())


def _dispatch_outcomes(record: dict[str, Any], events: list[Any]) -> list[dict[str, Any]]:
    requests = [call for e in events if e.event_type == "scripted_model_response"
                for call in e.payload["calls"]]
    dispatches = {e.payload["call_id"]: e.payload for e in events
                  if e.event_type == "teammate_boundary_call"}
    returns = {e.payload["call_id"]: e.payload for e in events
               if e.event_type == "teammate_boundary_return"}
    outcomes = []
    for request, call in zip(requests, record["agent"]["tool_calls"]):
        call_id = request["call_id"]
        start = dispatches.get(call_id)
        finish = returns.get(call_id)
        pose_changed = bool(start and finish and start["state_before"]["environment"]["robot"]
                            != finish["state_after"]["environment"]["robot"])
        outcomes.append({
            "call_id": call_id,
            "tool": request["name"],
            "requested_arguments": request["arguments"],
            "dispatched": start is not None,
            "rejected_before_dispatch": start is None,
            "movement_observed": pose_changed,
            "source": finish["source"] if finish else None,
            "agent_result": call["result"],
        })
    return outcomes


def run_final_case(
    scenario_id: str, output_dir: Path | str, *, seed: int = 42, control: str = "valid"
) -> dict[str, Any]:
    """Run one scenario with fresh actual layers and write its trace and official result.

    Only S10 supports the stale_action control. Invalid cases or controls raise ValueError.
    A pre-existing output directory raises FileExistsError.
    """
    from declarative.belief_graph import BeliefMemory
    from procedural.agent import run_agent
    from scripts.tool_wiring import build_tool_registry
    from sensorimotor import create_sensorimotor

    if scenario_id not in FINAL_SCENARIOS or (
        control != "valid" and (scenario_id, control) != ("S10", "stale_action")
    ):
        raise ValueError(f"Unknown final canonical case/control: {scenario_id}/{control}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    origins = verify_imports()
    question, expected, scope = CASE_SCOPE[scenario_id]
    if control == "stale_action":
        scope += " The fault script requests simulated motion without rechecking."
    config = json.loads((ROOT / "sensorimotor/scenarios/scenario_a.json").read_text("utf-8"))
    config["name"] = f"role4_{scenario_id.lower()}"
    obstacle = deepcopy(config["obstacles"][0])
    if scenario_id == "S04":
        config["sensors"]["lidar"][0]["confidence"] = 0.25
    if scenario_id == "S10":
        config["obstacles"] = []
    world = create_sensorimotor(config, seed=seed)
    world.env.reset()
    recorder = TraceRecorder(scenario_id)
    official = EvaluationLogger(output / "official")
    run_id = output.name

    def emit(kind: str, payload: dict[str, Any]) -> None:
        recorder.emit(kind, payload)
        official.log_event(run_id, kind, payload, event_id=f"{run_id}:{len(recorder.events)}")

    memory = BeliefMemory(clock=world.env.now_iso,
                          event_callback=lambda kind, payload: emit("canonical_" + kind, payload))
    adapter = CanonicalMemoryAdapter(memory)
    labels = {
        "per_layer_backend": {"declarative": "real", "procedural": "real", "sensorimotor":
                              "mixed" if scenario_id == "S05" else
                              "not_exercised" if scenario_id == "S09" else "real"},
        "environment": "simulated",
        "model_execution_mode": "scripted_llm",
        "hosted_reliability": "not_measured",
        "human_semantic_review": "pending",
        "fixture_origin": "role4_synthetic_scenario",
        "all_real_tools": scenario_id not in {"S05", "S09"},
        "scope": scope,
    }

    def snapshot() -> dict[str, Any]:
        return {"memory": adapter.snapshot(), "environment": world.env.get_state()}

    def change_world() -> None:
        before_change = world.env.get_state()
        world.env.advance_time(1)
        world.env.apply_change({"type": "add_obstacle", "obstacle": obstacle})
        emit("role4_world_change", {"before": before_change, "after": world.env.get_state(),
                                  "notice": "The scene fixture changed after the first observation."})

    try:
        seed_result = _seed_belief(scenario_id, memory)
        if seed_result is not None and not ToolResult.model_validate(seed_result).ok:
            raise ValueError(f"Canonical memory rejected the Role 4 scenario seed: {seed_result}")
        registry, sources = build_tool_registry(use_real=True, memory=memory, sensorimotor=world)
        require_real_tools(registry, sources, memory, world)
        if scenario_id == "S05":
            sources["read_lidar"] = f"{S05_REAL_SOURCE} + {S05_FIXTURE_SOURCE}"
        before = snapshot()
        emit("teammate_run_start", {"run_id": run_id, "question": question, "expected": expected,
                                   "labels": labels, "tool_sources": sources, "seed_receipt": seed_result,
                                   "state_before": before})
        plan = _plan(scenario_id, control, change_world)
        script = OfflineScript(plan, emit)
        lidar_reads = 0

        def instrument(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def invoke(**kwargs: Any) -> dict[str, Any]:
                nonlocal lidar_reads
                call_id = script.current_calls[0]["call_id"]
                source = sources[name]
                if name == "read_lidar":
                    lidar_reads += 1
                    source = (S05_FIXTURE_SOURCE if scenario_id == "S05" and lidar_reads == 2
                              else S05_REAL_SOURCE)
                emit("teammate_boundary_call", {"call_id": call_id, "tool": name, "arguments": kwargs,
                                                "source": source, "state_before": snapshot()})
                if source == S05_FIXTURE_SOURCE:
                    timestamp = world.env.now_iso()
                    reading = SensorReading(schema_version=SCHEMA_VERSION, sensor="lidar_secondary",
                                            value=150, unit="cm", status="clear",
                                            timestamp=timestamp, confidence=0.8)
                    raw = success_result(name, reading.model_dump(mode="json"), timestamp)
                else:
                    raw = fn(**kwargs)
                emit("teammate_boundary_return", {"call_id": call_id, "tool": name, "raw": raw,
                                                 "canonical_envelope_valid": is_valid_contract(ToolResult, raw),
                                                 "source": source, "state_after": snapshot()})
                return raw
            return invoke

        result = run_agent(question, script, {name: instrument(name, fn) for name, fn in registry.items()},
                           max_steps=len(plan), known_subjects={"path_A": "final route fixture",
                                                              "robot": "robot with no battery tool"})
        record = {
            "scenario_id": scenario_id,
            "run_id": run_id,
            "control": control,
            "question": question,
            "expected": expected,
            "state_before": before,
            "state_after": snapshot(),
            "agent": asdict(result),
            "labels": labels,
            "tool_sources": sources,
            "import_origins": origins,
            "structured_answer_claims": None,
            "answer_origin": "scripted_fixture",
            "pending_checks": ["human_answer_semantics"],
        }
        record["dispatch_outcomes"] = _dispatch_outcomes(record, recorder.events)
        record["trace_consistent"] = trace_consistent(record, recorder.events)
        evaluation = _evaluate(record, recorder.events)
        record["evaluation"] = evaluation.to_dict()
        record["failure_layers"] = {c["name"]: c["layer"] for c in evaluation.checks if not c["passed"]}
        record["expected_failures"] = list(KNOWN_FAILURES.get((scenario_id, control), ()))
        record["expectation_met"] = evaluation.failure_reasons == record["expected_failures"]
        emit("actual_agent_outcome", {"agent": record["agent"], "state_after": record["state_after"],
                                     "evaluation": record["evaluation"]})
        with EventLogger(output / "trace.jsonl") as stream:
            for event in recorder.events:
                stream.record(event)
        write_json(output / "run.json", record)
        official.write_test_log(scenario_id, run_id, {
            "question": question, "expected": expected, "state_before": before,
            "state_after": record["state_after"], "answer": result.answer,
            "tool_calls": result.tool_calls, "checks": evaluation.checks, "labels": labels,
            "result": "PASS" if evaluation.passed else "FAIL",
        })
        return record
    finally:
        memory.close()


def verify_final_case_artifacts(output_dir: Path | str) -> dict[str, int]:
    """Replay checks and compare the canonical trace and both logger artifacts."""
    output = Path(output_dir)
    record = json.loads((output / "run.json").read_text("utf-8"))
    events = read_events(output / "trace.jsonl")
    replay = _evaluate(record, events)
    official = output / "official"
    logged = json.loads(next(official.glob("*.json")).read_text("utf-8"))
    official_events = [json.loads(line) for line in (official / "events.jsonl").read_text("utf-8").splitlines()]
    expected_run = {
        "question": record["question"], "expected": record["expected"],
        "state_before": record["state_before"], "state_after": record["state_after"],
        "tool_calls": record["agent"]["tool_calls"], "answer": record["agent"]["answer"],
        "checks": replay.checks, "labels": record["labels"],
        "result": "PASS" if replay.passed else "FAIL",
    }
    if (replay.checks != record["evaluation"]["checks"]
            or replay.failure_reasons != record["evaluation"]["failure_reasons"]
            or replay.passed != record["evaluation"]["passed"]
            or record["dispatch_outcomes"] != _dispatch_outcomes(record, events)
            or not trace_consistent(record, events)
            or any(logged[key] != value for key, value in expected_run.items())
            or len(events) != len(official_events)
            or not all(o["details"] == e.payload and o["event_type"] == e.event_type
                       for o, e in zip(official_events, events))):
        raise ValueError(f"Inconsistent final case artifacts: {output}")
    return {"cases_verified": 1, "json_jsonl_files_parsed": 4}
