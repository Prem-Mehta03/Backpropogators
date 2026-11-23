"""Run the ten Role 4 scenarios and retain evidence for each measured outcome."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.logger import EvaluationLogger
from contracts.version import SCHEMA_VERSION
from evaluation.role4.integration.conformance import probe_registry, validate_tool_output
from evaluation.role4.integration.runner import load_scenario
from evaluation.role4.integration.teammate_runner import (
    CONTROLS,
    run_teammate_case,
    verify_artifacts,
)
from evaluation.role4.logger import read_events, write_json

CASES = tuple(f"S{number:02}" for number in range(1, 11))
ORIGINAL_CASES = {"S01", "S02", "S03", "S07", "S08"}
EXPECTED = dict(zip(CASES, (
    "Use newer strong LiDAR instead of a clear historical map, preserve history, explain and avoid unsafe movement.",
    "Report current clear LiDAR with its time and confidence and distinguish the older blocked map.",
    "Attribute the user, observed and older blue claims separately.",
    "Keep a strong older belief when weak sensor evidence contradicts it and communicate uncertainty.",
    "Keep disagreeing live readings separate, dispute the conclusion and request more evidence.",
    "Separate stale belief and current observation and attribute both to their times.",
    "Report missing memory and unavailable evidence, abstain and avoid acting on invented facts.",
    "Keep the user claim in its own perspective and apply the independently observed status.",
    "Identify missing provenance and prevent an unsupported high-confidence conclusion.",
    "After a world change, recheck the earlier sensor before answering or dispatching an action.",
)))
GAP_LAYERS = {
    "canonical_beliefs": "declarative",
    "canonical_supersession": "declarative",
    "perspectives_retained": "declarative",
    "update_matches_returned_evidence": "procedural",
    "no_movement_on_blocked_evidence": "procedural",
    "trace_dispatch_consistency": "evaluation",
    "result_payload_contract": "evaluation",
    "fresh_state": "evaluation",
    "current_lidar_status": "sensorimotor",
    "three_distinct_claims": "declarative",
    "user_claim_preserved": "declarative",
    "empty_memory_observed": "declarative",
}


def _layer(name: str) -> str:
    if name in GAP_LAYERS:
        return GAP_LAYERS[name]
    if name.startswith(("final_belief", "preserved_perspective", "required_update")):
        return "declarative"
    if name.startswith(("initial_state", "input_events", "trace_integrity", "state_replay")):
        return "evaluation"
    return "procedural"


def _reference(scenario: str, case: Path, fault: bool) -> dict:
    from evaluation.role4.final_reference import REFERENCE_FAULT_CHECKS, run_final_reference

    raw_dir = case / "raw"
    name = "injected_fault" if fault else "valid"
    outcome = run_final_reference(scenario, case_name=name, injected_fault=fault, output_dir=raw_dir)
    if outcome.run is None or outcome.run.result is None:
        raise RuntimeError(f"{scenario}/{name}: reference runner returned {outcome.error}")
    run = outcome.run
    trace = read_events(raw_dir / f"{run.run_id}_trace.jsonl")
    if trace[:len(run.events)] != run.events or trace[-1].payload != run.result.to_dict():
        raise ValueError(f"{scenario}/{name}: trace disagrees with recorded result")
    returns = {e.payload["call_id"]: e.payload for e in run.events
               if e.event_type in {"tool_result", "tool_error"}}
    tool_calls = [{"step": i, "tool": e.payload["tool_name"], "args": e.payload["arguments"],
                   "result": returns[e.payload["call_id"]]}
                  for i, e in enumerate((e for e in run.events if e.event_type == "tool_call"), 1)]
    answer = next(e.payload for e in run.events if e.event_type == "agent_response")
    result = run.result
    failure_names = {check["name"] for check in result.checks if not check["passed"]}
    metadata = run.integration_metadata or {}
    return {
        "question": run.user_query, "tool_calls": tool_calls,
        "state_before": {"beliefs": [b.to_dict() for b in run.initial_beliefs],
                         "environment": run.initial_environment_state},
        "state_after": {"beliefs": [b.to_dict() for b in run.final_beliefs],
                        "environment": metadata.get("final_environment_state", run.initial_environment_state)},
        "answer": answer["text"], "structured_answer_claims": answer["claims"],
        "labels": {"per_layer_backend": {layer: "reference" for layer in
                                         ("declarative", "sensorimotor", "procedural")},
                   "environment": "simulated", "model_execution_mode": "deterministic_reference",
                   "fixture_origin": "role4_reference", "human_semantic_review": "pending"},
        "criteria_scope": "reference_structured_behavior", "checks": result.checks,
        "result": "PASS" if result.passed else "FAIL",
        "injected_fault_origin": "procedural_reference" if fault else None,
        "expectation_met": (not result.passed and
                            set(REFERENCE_FAULT_CHECKS[scenario]) <= failure_names
                            if fault else result.passed),
    }


def _canonical(scenario: str, case: Path, seed: int, control: str = "valid") -> dict:
    raw_dir = case / "raw"
    if scenario in ORIGINAL_CASES:
        record = run_teammate_case(scenario, raw_dir, control, seed=seed)
        if verify_artifacts(case)["cases_verified"] != 1:
            raise ValueError(f"{scenario}/{control}: canonical artifacts missing")
    else:
        from evaluation.role4.integration.final_cases import run_final_case, verify_final_case_artifacts

        kwargs = {} if control == "valid" else {"control": control}
        record = run_final_case(scenario, raw_dir, seed=seed, **kwargs)
        verify_final_case_artifacts(raw_dir)
    agent = record["agent"]
    evaluation = record["evaluation"]
    checks = list(evaluation["checks"])
    final_checks = _canonical_original_checks(scenario, record) if control == "valid" else []
    checks.extend(final_checks)
    check_payloads = []
    for call in agent["tool_calls"]:
        try:
            validate_tool_output(call["tool"], call["result"])
        except ValueError as exc:
            check_payloads.append(str(exc))
    checks.append({"name": "result_payload_contract", "passed": not check_payloads,
                   "detail": "; ".join(check_payloads) or "Agent results have canonical envelopes and payloads."})
    scoped = scenario == "S07" and control == "valid"
    return {
        "question": record.get("question", load_scenario(scenario).user_query),
        "state_before": record["state_before"], "state_after": record["state_after"],
        "tool_calls": agent["tool_calls"], "answer": agent["answer"], "agent_error": agent["error"],
        "structured_answer_claims": None, "labels": record["labels"], "checks": checks,
        "result": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "criteria_scope": "unsupported_temperature_probe" if scoped else "observable_scripted_behavior",
        "expectation_met": record["expectation_met"] and not check_payloads and all(c["passed"] for c in final_checks),
        "pending_checks": record.get("pending_checks", ["human_answer_semantics"]),
        "dispatch_outcomes": record.get("dispatch_outcomes", []),
        "tool_sources": record.get("tool_sources", {}),
    }


def _canonical_original_checks(scenario: str, record: dict) -> list[dict]:
    """Add final scenario-specific evidence checks without changing the historical build."""
    if scenario not in ORIGINAL_CASES:
        return []
    before = record["state_before"]["memory"]["nodes"]
    after = record["state_after"]["memory"]["nodes"]
    calls = record["agent"]["tool_calls"]
    if scenario in {"S01", "S02"}:
        status = "blocked" if scenario == "S01" else "clear"
        readings = [c["result"]["data"] for c in calls if c["tool"] == "read_lidar" and c["result"]["ok"]]
        passed = any(
            reading["status"] == status and any(
                b["perspective"] == "agent_sensor" and b["object"] == status
                and (b["source"], b["timestamp"], b["confidence"])
                == (reading["sensor"], reading["timestamp"], reading["confidence"])
                for b in after
            ) for reading in readings
        )
        return [{"name": "current_lidar_status", "passed": passed,
                 "detail": f"The {status} reading is carried into memory with its original source, time and confidence."}]
    if scenario == "S03":
        expected = {("red", "user", "user"), ("blue", "third_party", "bot_02"),
                    ("brown", "agent_sensor", "camera_front")}
        claims = {(b["object"], b["perspective"], b["source"]) for b in after
                  if b["subject"] == "box_01" and b["predicate"] == "color"}
        return [{"name": "three_distinct_claims", "passed": claims == expected,
                 "detail": "The observed brown, user red and bot_02 blue claims retain their own provenance."}]
    if scenario == "S07":
        passed = any(c["tool"] == "query_belief" and c["result"]["ok"] and c["result"]["data"] == []
                     or c["tool"] == "query_belief" and not c["result"]["ok"]
                     and c["result"]["error"]["code"] == "NOT_FOUND" for c in calls)
        return [{"name": "empty_memory_observed", "passed": passed,
                 "detail": "The actual query reports an empty list, separately from the unsupported sensor tool."}]
    passed = (len(before) == 1 and before[0]["perspective"] == "user" and before[0] in after
              and any(b["perspective"] == "agent_sensor" and b["object"] == "blocked" for b in after))
    return [{"name": "user_claim_preserved", "passed": passed,
             "detail": "The stored user claim is preserved while actual LiDAR adds a separate blocked observation."}]


def _strict_json(path: Path) -> dict:
    def invalid(value: str) -> None:
        raise ValueError(f"{path}: non-JSON number {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def _write_case(case: Path, scenario: str, scope: str, trial: int, control: str, data: dict) -> dict:
    run_id = f"{scenario}_{scope}_{trial:02}_{control}"
    checks = [{**c, "layer": c.get("layer") or _layer(c["name"])} for c in data["checks"]]
    failures = [c["name"] for c in checks if not c["passed"]]
    result = {"expected": EXPECTED[scenario], **data, "checks": checks, "scenario_id": scenario,
              "scope": scope, "control": control, "trial": trial,
              "failure_layers": sorted({c["layer"] for c in checks if not c["passed"]}),
              "failure_reasons": failures}
    if result["result"] != ("FAIL" if failures else "PASS"):
        raise ValueError(f"{run_id}: checks disagree with result")
    path = EvaluationLogger(case).write_test_log(scenario, run_id, result)
    path.rename(case / "run.json")
    stored = _strict_json(case / "run.json")
    if stored != {"test_id": scenario, "run_id": run_id, "schema_version": SCHEMA_VERSION, **result}:
        raise ValueError(f"{run_id}: final log does not round-trip")
    return stored


def _metric_rows(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for record in records:
        groups[(record["scope"], record["scenario_id"], record["control"])].append(record)
    metrics = []
    for (scope, case, control), runs in sorted(groups.items()):
        counts = Counter(r["result"] for r in runs)
        signatures = {(r["result"], tuple((c["name"], c["passed"]) for c in r["checks"]),
                       tuple(c["tool"] for c in r["tool_calls"]))
                      for r in runs}
        metrics.append({
            "scope": scope, "scenario_id": case, "control": control,
            "criteria_scope": runs[0]["criteria_scope"], "runs": len(runs),
            "passes": counts["PASS"], "fails": counts["FAIL"],
            "pass_rate": counts["PASS"] / len(runs),
            "expected_outcomes": sum(r["expectation_met"] for r in runs),
            "stable_tool_sequence_and_checks": len(signatures) == 1,
            "stable_before_after_state": all(
                (r["state_before"], r["state_after"]) == (runs[0]["state_before"], runs[0]["state_after"])
                for r in runs
            ),
            "failure_reasons": sorted({reason for r in runs for reason in r["failure_reasons"]}),
            "failure_layers": sorted({layer for r in runs for layer in r["failure_layers"]}),
        })
    return metrics


def _print_demo(record: dict) -> None:
    print(f"\n{record['scenario_id']} {record['scope']} / {record['criteria_scope']}: {record['result']}")
    print(f"  Question: {record['question']}")

    def show_beliefs(label: str, state: dict) -> None:
        print(f"  Beliefs {label}:")
        nodes = state.get("memory", {}).get("nodes", [])
        for belief in nodes:
            print(f"    {belief['belief_id']} {belief['subject']}/{belief['predicate']} = {belief['object']} "
                  f"[{belief['perspective']}, {belief['source']}, {belief['confidence']:.2f}, {belief['status']}]")
        if not nodes:
            print("    No records")

    world = record["state_before"]["environment"]
    print(f"  Simulated world: {world.get('scenario', 'fixture')}, "
          f"{world.get('lighting', {}).get('name', 'lighting unavailable')}, "
          f"time {world.get('time', 'unavailable')}")
    show_beliefs("before", record["state_before"])
    for call in record["tool_calls"]:
        result = call["result"]
        data = result["data"]
        if not result["ok"]:
            detail = result["error"]["code"]
        elif isinstance(data, list):
            detail = f"{len(data)} records"
        elif isinstance(data, dict) and "sensor" in data:
            detail = (f"{data['sensor']} {data['status']}, {data['value']} {data['unit'] or ''}, "
                      f"confidence {data['confidence']:.2f}, {data['timestamp']}")
        elif isinstance(data, dict) and "belief_id" in data:
            detail = f"{data['belief_id']} {data['object']} ({data['status']})"
        else:
            detail = repr(data)
        print(f"  {call['tool']} -> {detail}")
    show_beliefs("after", record["state_after"])
    print(f"  Scripted answer: {record['answer']}")
    if record.get("agent_error"):
        print(f"  Agent error: {record['agent_error']}")


def run_suite(output: Path, *, trials: int, seed: int, scenarios: tuple[str, ...] = CASES,
              controls: bool = True, show_cases: bool = False, blocked: list | None = None) -> dict:
    """Run isolated repeats plus single-injection controls and save summary, CSV and traces."""
    if not (1 <= trials <= 50) or len(set(scenarios)) != len(scenarios) or not scenarios or not set(scenarios) <= set(CASES):
        raise ValueError("Use 1–50 trials and distinct known scenarios")
    output.mkdir(parents=True, exist_ok=False)
    records = []

    def collect(case: Path, scenario: str, scope: str, trial: int, control: str, data: dict) -> None:
        record = _write_case(case, scenario, scope, trial, control, data)
        record["evidence"] = (case / "run.json").relative_to(output).as_posix()
        records.append(record)
        if show_cases and trial == 1 and scope == "canonical":
            _print_demo(record)

    for trial in range(1, trials + 1):
        for scenario in scenarios:
            directory = output / f"trial_{trial:02}"
            ref = directory / "reference" / scenario
            actual = directory / "canonical" / scenario
            collect(ref, scenario, "reference", trial, "valid", _reference(scenario, ref, False))
            collect(actual, scenario, "canonical", trial, "valid", _canonical(scenario, actual, seed))
    if controls:
        for scenario in scenarios:
            case = output / "controls" / "reference" / scenario
            collect(case, scenario, "reference_control", 1, "injected_fault", _reference(scenario, case, True))
        for control in (c for c in CONTROLS if c != "valid"):
            scenario = {"unavailable_evidence": "S07", "movement_attempt": "S08"}.get(control, "S01")
            if scenario in scenarios:
                case = output / "controls" / "canonical" / f"{scenario}_{control}"
                collect(case, scenario, "canonical_control", 1, control, _canonical(scenario, case, seed, control))
        if "S10" in scenarios:
            case = output / "controls" / "canonical" / "S10_stale_action"
            collect(case, "S10", "canonical_control", 1, "stale_action",
                    _canonical("S10", case, seed, "stale_action"))
    conformance = probe_registry(output / "contract_conformance.json", seed)
    metrics = _metric_rows(records)
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows({**r, "failure_reasons": "|".join(r["failure_reasons"]),
                          "failure_layers": "|".join(r["failure_layers"])} for r in metrics)
    counts = {}
    for scope in sorted({r["scope"] for r in records}):
        selected = [r for r in records if r["scope"] == scope]
        passed = sum(r["result"] == "PASS" for r in selected)
        counts[scope] = {"runs": len(selected), "passes": passed, "fails": len(selected) - passed,
                         "pass_rate": passed / len(selected),
                         "expected_outcomes": sum(r["expectation_met"] for r in selected)}
    summary = {
        "schema_version": SCHEMA_VERSION, "scenarios": list(scenarios), "trials": trials, "seed": seed,
        "repeated_run_mode": "same fixed seed and fresh state per case",
        "pass_rate_basis": "checks within each run's declared criteria_scope",
        "hosted_reliability": "not_measured", "human_semantic_review": "pending",
        "blocked_network_attempts": len(blocked or []), "counts": counts, "metrics": metrics,
        "conformance": {"passed": conformance["passed"], "tools": conformance["distinct_tools"],
                        "samples": len(conformance["samples"]), "evidence": "contract_conformance.json"},
        "unexpected_outcomes": [r["evidence"] for r in records if not r["expectation_met"]],
        "unstable_case_groups": [f"{m['scope']}/{m['scenario_id']}/{m['control']}" for m in metrics
                                 if not (m["stable_tool_sequence_and_checks"] and m["stable_before_after_state"])],
        "canonical_behavior_gaps": [r["evidence"] for r in records
                                    if r["scope"] in {"canonical", "canonical_control"} and
                                    (r["result"] == "FAIL" or r["criteria_scope"] == "unsupported_temperature_probe")],
        "runs": [{k: r[k] for k in ("test_id", "run_id", "scope", "trial", "control", "criteria_scope", "result",
                                   "expectation_met", "failure_reasons", "failure_layers", "evidence", "labels")}
                 for r in records],
    }
    write_json(output / "summary.json", summary)
    return summary
