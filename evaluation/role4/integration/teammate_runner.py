"""Role 4 composition root for actual teammate implementations and offline scripts."""
from copy import deepcopy
from dataclasses import asdict
import importlib
import json
from pathlib import Path

from contracts.models import ToolResult
from evaluation.logger import EvaluationLogger
from evaluation.role4.integration.canonical import CanonicalMemoryAdapter, belief_view, sensor_evidence
from evaluation.role4.integration.trace_recorder import TraceRecorder
from evaluation.role4.integration.teammate_policies import evaluate_teammate
from evaluation.role4.logger import EventLogger, write_json, read_events
from evaluation.role4.models import load_scenarios

ROOT = Path(__file__).resolve().parents[3]
CONTROLS = ("valid", "invalid_arguments", "malformed_arguments", "malformed_envelope",
            "missing_tool", "unavailable_evidence", "provenance_guard", "invented_downgrade",
            "unsupported_update", "confidence_override", "premature_answer", "step_limit",
            "llm_error", "movement_attempt", "downgrade")


def verify_imports():
    origins = {}
    for name in ("contracts.models", "declarative.belief_graph", "sensorimotor", "procedural.agent",
                 "evaluation.logger", "scripts.tool_wiring"):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if ROOT not in path.parents:
            raise RuntimeError(f"Import outside integration checkout: {name}: {path}")
        origins[name] = str(path)
    return origins


def require_real_tools(registry, sources, memory, world):
    """Reject build_tool_registry's automatic fakes, including falsely labelled callables."""
    from scripts.tool_wiring import MEMORY_TOOLS, SENSOR_TOOLS, MEMORY_SOURCE, SENSORIMOTOR_SOURCE
    for tool in MEMORY_TOOLS + SENSOR_TOOLS:
        expected = MEMORY_SOURCE if tool in MEMORY_TOOLS else SENSORIMOTOR_SOURCE
        owner = getattr(registry.get(tool), "__self__", None)
        owners = (memory,) if tool in MEMORY_TOOLS else (world.sensors, world.actions)
        if sources.get(tool) != expected or not any(owner is x for x in owners):
            raise RuntimeError(f"All-real composition rejected fallback/missing tool: {tool}")


def trace_consistent(record, events):
    requests = [c for e in events if e.event_type == "scripted_model_response" for c in e.payload.get("calls", [])]
    outcomes = record["agent"]["tool_calls"]
    calls = [e.payload for e in events if e.event_type == "teammate_boundary_call"]
    returns = [e.payload for e in events if e.event_type == "teammate_boundary_return"]
    if len(requests) != len(outcomes) or len(calls) != len(returns):
        return False
    if any(r["name"] != o["tool"] for r, o in zip(requests, outcomes)):
        return False
    indexed = {r["call_id"]: r for r in requests}
    if len(indexed) != len(requests):
        return False
    for call, result in zip(calls, returns):
        if call["call_id"] != result["call_id"] or call["tool"] != result["tool"]:
            return False
        if indexed.get(call["call_id"], {}).get("name") != call["tool"]:
            return False
        position = next(i for i, r in enumerate(requests) if r["call_id"] == call["call_id"])
        if call["arguments"] != outcomes[position]["args"]:
            return False
        if result["canonical_envelope_valid"] and result["raw"] != outcomes[position]["result"]:
            return False
        if not result["canonical_envelope_valid"] and outcomes[position]["result"].get("error", {}).get("code") != "INTERNAL":
            return False
    if returns and returns[-1]["state_after"] != record["state_after"]:
        return False
    return True


def verify_artifacts(output_dir):
    """Replay observable checks and compare detailed traces with official logger records."""
    from scripts.tool_wiring import MEMORY_TOOLS, SENSOR_TOOLS, MEMORY_SOURCE, SENSORIMOTOR_SOURCE
    output = Path(output_dir)
    parsed = 0
    for path in output.rglob("*"):
        if path.suffix == ".json":
            json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            parsed += 1
        elif path.suffix == ".jsonl":
            for line in path.read_text().splitlines():
                json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            parsed += 1
    runs = list(output.glob("*/run.json"))
    for path in runs:
        record = json.loads(path.read_text())
        events = read_events(path.parent / "trace.jsonl")
        assert trace_consistent(record, events), path
        actual = evaluate_teammate(record)
        assert actual.checks == record["evaluation"]["checks"] and actual.failure_reasons == record["evaluation"]["failure_reasons"], path
        assert record["structured_answer_claims"] is None and record["labels"]["human_semantic_review"] == "pending"
        assert not any("tests.procedural.fakes" in source for source in record["tool_sources"].values())
        if record["labels"]["all_real_tools"]:
            for name in MEMORY_TOOLS + SENSOR_TOOLS:
                assert record["tool_sources"][name] == (MEMORY_SOURCE if name in MEMORY_TOOLS else SENSORIMOTOR_SOURCE)
        for origin in record["import_origins"].values():
            assert ROOT in Path(origin).resolve().parents
        official_events = [json.loads(line) for line in (path.parent / "official/events.jsonl").read_text().splitlines()]
        assert len(official_events) == len(events)
        assert len({event["event_id"] for event in official_events}) == len(events)
        assert all(o["event_type"] == e.event_type and o["details"] == e.payload for o, e in zip(official_events, events))
        official_run = json.loads(next((path.parent / "official").glob("*.json")).read_text())
        assert official_run["tool_calls"] == record["agent"]["tool_calls"] and official_run["state_after"] == record["state_after"]
    return {"cases_verified": len(runs), "json_jsonl_files_parsed": parsed}


class OfflineScript:
    """Scripted LLM backend. Adaptive calls use actual returned envelopes, never guessed evidence."""
    def __init__(self, plan, emit):
        self.plan = list(plan)
        self.emit = emit
        self.count = 0
        self.current_calls = []

    def chat(self, messages, tools=None, tool_choice=None):
        from procedural.llm_client import LLMResponse, ToolCall
        self.count += 1
        self.emit("scripted_model_request", {"model_call": self.count, "messages": deepcopy(messages)})
        item = self.plan.pop(0) if self.plan else "Script exhausted; evidence remains pending."
        if callable(item):
            item = item(messages)
        if isinstance(item, Exception):
            self.emit("scripted_model_error", {"error_type": type(item).__name__, "message": str(item)})
            raise item
        if isinstance(item, str):
            self.current_calls = []
            self.emit("scripted_model_response", {"text": item, "calls": [], "answer_origin": "scripted_fixture"})
            return LLMResponse(item)
        name, args, *bad = item
        call_id = f"request_{self.count:03}"
        self.current_calls = [{"call_id": call_id, "name": name, "arguments": deepcopy(args)}]
        self.emit("scripted_model_response", {"text": None, "calls": self.current_calls,
                                             "arguments_error": bad[0] if bad else None})
        return LLMResponse(None, [ToolCall(call_id, name, args, bad[0] if bad else None)])


def _plan(scenario, control, old_id):
    from procedural.llm_client import LLMClientError
    subject = "box_01" if scenario == "S03" else "room" if scenario == "S07" else "path_A"
    query = ("query_belief", {"subject": subject})
    sensor = ("read_camera", {"target": "box_01"}) if scenario == "S03" else ("read_lidar", {"direction": "front"})
    answer = "Scripted fixture: consulted memory and sensor tools; see their attributed results."

    def update(messages):
        envelope = json.loads(messages[-1]["content"])
        evidence = sensor_evidence(envelope)
        if evidence is None:
            raise ValueError("Script cannot invent missing sensor evidence")
        if control == "unsupported_update":
            evidence["object"] = "clear"  # deliberate contradiction to actual blocked LiDAR
        if control == "confidence_override":
            evidence["confidence"] = 0.1
        return "update_belief", evidence

    if control == "step_limit":
        return ["Premature scripted answer."] * 2
    if control == "llm_error":
        return [LLMClientError("Role 4 scripted transport failure")]
    if control == "invalid_arguments":
        return [query, ("read_lidar", {"direction": 5}), sensor, answer]
    if control == "malformed_arguments":
        return [query, ("read_lidar", {}, "injected malformed JSON"), sensor, answer]
    if control in ("missing_tool", "malformed_envelope", "unavailable_evidence"):
        return [query, sensor, answer]
    if control == "provenance_guard":
        return [query, ("update_belief", {"subject": subject, "predicate": "status", "object": "clear",
                "source": "imaginary_sensor", "confidence": 0.99, "perspective": "agent_sensor", "reason": "fault fixture"}), sensor, answer]
    if control == "invented_downgrade":
        return [query, sensor, ("downgrade_belief", {"belief_id": "b_999999", "new_confidence": 0.2, "reason": "fault fixture"}), answer]
    if control == "downgrade":
        return [query, sensor, ("downgrade_belief", {"belief_id": old_id, "new_confidence": 0.2, "reason": "returned sensor contradicts history"}), answer]
    if control == "movement_attempt":
        return [query, sensor, ("move_forward", {"distance_cm": 20}), answer]
    if scenario == "S07":
        return [query, query, ("read_temperature", {}), "Scripted temperature abstention; teammate temperature API absent."]
    prefix = ["Premature scripted answer."] if control == "premature_answer" else []
    return prefix + [query, sensor, update, ("get_belief_history", {"subject": subject}),
                     ("detect_conflict", {"subject": subject, "predicate": "color" if scenario == "S03" else "status"}), answer]


def run_teammate_case(scenario_id, output_dir, control="valid"):
    """Run fresh canonical layers locally; outputs preserve raw evidence and pending semantics."""
    from declarative.belief_graph import BeliefMemory
    from declarative.seed import seed_bot_02_record
    from procedural.agent import run_agent
    from sensorimotor import create_sensorimotor
    from scripts.tool_wiring import build_tool_registry

    if scenario_id not in ("S01", "S02", "S03", "S07", "S08") or control not in CONTROLS:
        raise ValueError("Unsupported milestone scenario/control")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    origins = verify_imports()
    config_name = "scenario_b" if scenario_id == "S03" else "scenario_a"
    config = json.loads((ROOT / f"sensorimotor/scenarios/{config_name}.json").read_text())
    if scenario_id == "S02":
        config["obstacles"] = []  # explicitly derived Scenario A: LiDAR reports its 400 cm range
    if control == "unavailable_evidence":
        config["sensors"]["lidar"][0]["available"] = False
    world = create_sensorimotor(config, seed=42)
    world.env.reset()
    recorder = TraceRecorder(scenario_id)
    official = EvaluationLogger(output / "official")
    run_id = f"{scenario_id}_{control}"

    def emit(kind, payload):
        recorder.emit(kind, payload)
        official.log_event(run_id, kind, payload, event_id=f"{run_id}:{len(recorder.events)}")

    memory = BeliefMemory(clock=world.env.now_iso, event_callback=lambda kind, details: emit("canonical_" + kind, details))
    adapter = CanonicalMemoryAdapter(memory)
    try:
        reference = next(s for s in load_scenarios(ROOT / "tests/role4/scenarios.json") if s.scenario_id == scenario_id)
        if scenario_id == "S03":
            # Exact demo data, not an assertion of the leader's Scenario B approval.
            memory.add_belief("box_01", "color", "red", "user", 0.9, "user", "2026-10-03T09:15:00Z")
            seed_bot_02_record(memory, "box_01", "color", "blue", 0.8, "2026-10-03T09:15:00Z")
        elif scenario_id != "S07":
            for belief in reference.initial_beliefs:
                emit("reference_seed_mapping", {"reference": belief.to_dict(), "canonical_receipt": adapter.seed_reference(belief)})
        registry, sources = build_tool_registry(use_real=True, memory=memory, sensorimotor=world)
        require_real_tools(registry, sources, memory, world)
        if control == "missing_tool":
            registry.pop("read_lidar")
            sources["read_lidar"] = "role4.disabled_tool_fault_fixture"
        if control == "malformed_envelope":
            registry["read_lidar"] = lambda **kwargs: {"tool": "read_lidar", "ok": True, "data": {}, "error": None}
            sources["read_lidar"] = "role4.reference_malformed_envelope_fixture"
        scoped_temperature = scenario_id == "S07" and control == "valid"
        labels = {"per_layer_backend": {"declarative": "real", "sensorimotor": "mixed" if scoped_temperature or control in ("missing_tool", "malformed_envelope") else "real", "procedural": "real"},
                  "environment": "simulated", "model_execution_mode": "scripted_llm", "hosted_reliability": "not_measured",
                  "scope": "temperature unsupported-tool probe; reference temperature evaluation remains separate" if scoped_temperature else "canonical memory, simulated tools, actual run_agent and EvaluationLogger",
                  "all_real_tools": not scoped_temperature and control not in ("missing_tool", "malformed_envelope"),
                  "human_semantic_review": "pending"}

        def snapshot():
            return {"memory": adapter.snapshot(), "environment": world.env.get_state()}

        before = snapshot()
        emit("teammate_run_start", {"run_id": run_id, "labels": labels, "tool_sources": sources, "state_before": before})
        old_id = before["memory"]["nodes"][0]["belief_id"] if before["memory"]["nodes"] else None
        script = OfflineScript(_plan(scenario_id, control, old_id), emit)

        def instrument(name, fn):
            def invoke(**kwargs):
                call_id = script.current_calls[0]["call_id"]
                emit("teammate_boundary_call", {"call_id": call_id, "tool": name, "arguments": kwargs,
                                                "source": sources[name], "implementation": fn.__module__ + "." + fn.__qualname__,
                                                "state_before": snapshot()})
                raw = fn(**kwargs)
                try:
                    ToolResult.model_validate(raw)
                    valid = True
                except ValueError:
                    valid = False
                emit("teammate_boundary_return", {"call_id": call_id, "tool": name, "raw": deepcopy(raw),
                                                  "canonical_envelope_valid": valid, "source": sources[name], "state_after": snapshot()})
                return raw
            return invoke

        wrapped = {name: instrument(name, fn) for name, fn in registry.items()}
        result = run_agent(reference.user_query, script, wrapped, max_steps=8 if control != "step_limit" else 2,
                           known_subjects={"path_A": "canonical path fixture", "box_01": "demo box", "room": "unsupported temperature query"})
        after = snapshot()
        record = {"scenario_id": scenario_id, "run_id": run_id, "control": control, "labels": labels,
                  "tool_sources": sources, "import_origins": origins, "reference_aliases": adapter.aliases,
                  "state_before": before, "state_after": after, "agent": asdict(result),
                  "canonical_views": [belief_view(b) for b in after["memory"]["nodes"]],
                  "structured_answer_claims": None, "answer_origin": "scripted_fixture",
                  "pending_checks": ["human_answer_semantics"] + (["leader_scenario_b_fixture_approval"] if scenario_id == "S03" else [])}
        record["trace_consistent"] = trace_consistent(record, recorder.events)
        requests = [c for e in recorder.events if e.event_type == "scripted_model_response" for c in e.payload.get("calls", [])]
        dispatches = {e.payload["call_id"]: e.payload for e in recorder.events if e.event_type == "teammate_boundary_call"}
        returns = {e.payload["call_id"]: e.payload for e in recorder.events if e.event_type == "teammate_boundary_return"}
        record["dispatch_outcomes"] = [{"call_id": r["call_id"], "tool": r["name"], "requested_arguments": r["arguments"],
            "dispatched": r["call_id"] in dispatches, "rejected_before_dispatch": r["call_id"] not in dispatches,
            "movement_observed": r["call_id"] in returns and
                dispatches[r["call_id"]]["state_before"]["environment"]["robot"] != returns[r["call_id"]]["state_after"]["environment"]["robot"],
            "agent_result": o["result"], "guard": o.get("guard")}
            for r, o in zip(requests, result.tool_calls)]
        evaluation = evaluate_teammate(record)
        record["evaluation"] = evaluation.to_dict()
        record["expected_failures"] = ["update_matches_returned_evidence"] if control == "unsupported_update" else ["no_movement_on_blocked_evidence"] if control == "movement_attempt" else []
        record["expectation_met"] = evaluation.failure_reasons == record["expected_failures"]
        # Agent outcomes include attempts rejected before any boundary dispatch.
        emit("actual_agent_outcome", {"agent": asdict(result), "state_after": after, "evaluation": evaluation.to_dict()})
        with EventLogger(output / "trace.jsonl") as stream:
            for event in recorder.events:
                stream.record(event)
        assert read_events(output / "trace.jsonl") == recorder.events
        write_json(output / "run.json", record)
        official.write_test_log(scenario_id, run_id, {"question": reference.user_query,
            "state_before": before, "tool_calls": result.tool_calls, "state_after": after, "answer": result.answer,
            "expected": {"observable_policy": "canonical_teammate_v1", "pending_checks": record["pending_checks"]},
            "checks": evaluation.checks, "result": "PASS" if evaluation.passed else "FAIL", "labels": labels})
        return record
    finally:
        memory.close()
