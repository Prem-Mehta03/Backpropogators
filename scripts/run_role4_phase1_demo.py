"""Run from any directory: python scripts/run_role4_phase1_demo.py."""

from pathlib import Path
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.role4.evaluator import evaluate
from evaluation.role4.logger import EventLogger, read_events, write_json
from evaluation.role4.models import load_scenarios
from evaluation.role4.stubs import scenario1_execution


def main() -> int:
    scenario = next(s for s in load_scenarios(ROOT / "tests/role4/scenarios.json") if s.scenario_id == "S01")
    output = ROOT / "evaluation/logs/role4/phase1"
    print("I Agent | Role 4 | Phase 1 evaluation demo (scripted fixtures)")
    print("Scenario S01: stored map = clear; LiDAR = blocked at 12 cm")
    results = []
    for valid in (True, False):
        run = scenario1_execution(scenario, valid=valid)
        result = evaluate(scenario, run)
        run.result = result
        results.append(result)
        log_path = output / f"{run.run_id}.jsonl"
        with EventLogger(log_path) as logger:
            logger.record_run(run, result)
        write_json(output / f"{run.run_id}_result.json", result.to_dict())
        write_json(output / f"{run.run_id}_run.json", run.to_dict())
        read_events(log_path)
        label = "VALID" if valid else "INTENTIONALLY INVALID"
        print(f"\n{label}: {'PASS' if result.passed else 'FAIL'} ({sum(c['passed'] for c in result.checks)}/{len(result.checks)} checks passed)")
        for reason in result.failure_reasons:
            print(f"  - {reason}")
        print(f"  Log: evaluation/logs/role4/phase1/{run.run_id}.jsonl")
    write_json(output / "summary.json", {
        "phase": 1, "execution": "stub", "backend_type": "reference",
        "model_execution_mode": "scripted_fixture", "teammate_modules_integrated": False,
        "results": [r.to_dict() for r in results],
    })
    expected_failures = {"required_tool:read_lidar", "required_tool:update_belief", "tool_order", "required_update:path_a_sensor",
                         "final_belief:path_a_sensor", "response_evidence", "acknowledge_conflict",
                         "response_claim:path_status", "response_claim:movement_safe"}
    failed_checks = {c["name"] for c in results[1].checks if not c["passed"]}
    if not results[0].passed or results[1].passed or failed_checks != expected_failures:
        print("\nDEMO ERROR: evaluator did not produce the expected pass/failure checks")
        return 1
    print("\nDemo verification: expected PASS and expected FAIL confirmed. No API key required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
