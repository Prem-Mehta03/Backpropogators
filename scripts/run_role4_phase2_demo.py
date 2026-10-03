"""Demonstrate reference integration, a procedural fault and contract rejection."""

from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.role4.logger import write_json
from evaluation.role4.integration.runner import load_s01, reference_backends, run_s01


def main():
    print("I Agent | Role 4 | Phase 2 reference-layer integration")
    print("Deterministic reference layers; teammate implementations are not integrated.")
    scenario = load_s01()
    outcomes = []
    cases = [("integrated_valid", {}, "A"), ("missing_lidar", {"skip_lidar": True}, "B"),
             ("malformed_sensor", {"malformed_lidar": True}, "C")]
    for name, faults, label in cases:
        outcome = run_s01(name, *reference_backends(scenario, **faults))
        outcomes.append(outcome)
        print(f"\nCase {label} ({name}): {outcome.status}")
        if outcome.run:
            result = outcome.run.result
            print(f"  {sum(c['passed'] for c in result.checks)}/{len(result.checks)} checks passed")
            for reason in result.failure_reasons:
                print(f"  - {reason}")
        else:
            print(f"  {outcome.error['message']}")
            print("  Aborted before evaluation; partial trace retained.")
    summary = {"phase": 2, "layer_source": "reference_layers", "backend_type": "reference",
               "layer_types": {name: "reference" for name in ("declarative", "procedural", "sensorimotor")},
               "model_execution_mode": "deterministic_reference", "teammate_modules_integrated": False,
               "cases": [{"case": case[0], "status": outcome.status,
                          "result": outcome.run.result.to_dict() if outcome.run else None, "error": outcome.error}
                         for case, outcome in zip(cases, outcomes)]}
    write_json(ROOT / "evaluation/logs/role4/phase2/summary.json", summary)
    expected_failures = {"required_tool:read_lidar", "required_tool:update_belief", "tool_order", "required_update:path_a_sensor",
                         "final_belief:path_a_sensor", "response_evidence", "acknowledge_conflict",
                         "response_claim:path_status", "response_claim:movement_safe"}
    checks = {c["name"] for c in outcomes[1].run.result.checks if not c["passed"]} if outcomes[1].run else set()
    verified = ([o.status for o in outcomes] == ["PASS", "FAIL", "CONTRACT ERROR"] and
                checks == expected_failures and "confidence" in (outcomes[2].error or {}).get("message", ""))
    print("\nArtifacts: evaluation/logs/role4/phase2/")
    print("Demo verification: expected PASS / FAIL / CONTRACT ERROR confirmed." if verified else "DEMO ERROR: unexpected outcomes")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
