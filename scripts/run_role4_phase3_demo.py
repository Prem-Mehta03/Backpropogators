"""Selected or complete Phase 3 reference demo; injected faults should be rejected."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.role4.logger import write_json
from evaluation.role4.policies import PHASE3_SCENARIOS, BehavioralPolicy, load_policies
from evaluation.role4.integration.runner import run_scenario
from evaluation.role4.reference_layers.conflict_procedural_reference import FAULTS

EXPECTED_FAULT_CHECKS = {
    "repeat_history": {"evidence_to_claim", "current_vs_history"},
    "collapse_perspectives": {"perspective_separation", "source_attribution"},
    "inflate_confidence": {"confidence_preserved", "confidence_threshold_policy"},
    "ignore_sensor": {"required_tool:read_camera", "all_sensor_perspectives"},
    "trust_user_and_move": {"forbidden_tool:move_forward", "user_vs_verified_observation"},
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all", *PHASE3_SCENARIOS), default="all")
    parser.add_argument("--backend", choices=("reference",), default="reference", help="Real/mixed backends require explicit API injection; none are installed")
    parser.add_argument("--minimum-confidence", type=float)
    parser.add_argument("--max-observation-age-seconds", type=float)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/logs/role4/phase3")
    args = parser.parse_args(argv)
    policies = load_policies()
    ids = PHASE3_SCENARIOS if args.scenario == "all" else (args.scenario,)
    cases = []
    verified = True
    print("I Agent | Phase 3 conflict, confidence and perspective evaluation | backend=reference")
    print("Deterministic reference layers. Real teammate integration: absent. Human semantic review: pending.")
    for scenario_id in ids:
        expected = policies[scenario_id]
        changes = {}
        if args.minimum_confidence is not None:
            changes["minimum_sensor_confidence"] = args.minimum_confidence
        if args.max_observation_age_seconds is not None:
            changes["maximum_observation_age_seconds"] = args.max_observation_age_seconds
        if changes:
            try:
                expected = BehavioralPolicy(replace(expected.execution, **changes), expected.claim_perspectives)
            except ValueError as exc:
                parser.error(str(exc))
        for valid in (True, False):
            fault = None if valid else FAULTS[expected.execution.mode]
            case_name = "valid" if valid else "injected_fault"
            outcome = run_scenario(scenario_id, case_name, expected_behavioral_policy=expected,
                                   injected_fault=fault, output_dir=args.output_dir)
            result = outcome.run.result.to_dict() if outcome.run else None
            failed_checks = {check["name"] for check in result["checks"] if not check["passed"]} if result else set()
            required_failures = set() if valid else EXPECTED_FAULT_CHECKS[fault]
            correct = outcome.status == ("PASS" if valid else "FAIL") and required_failures <= failed_checks
            verified &= correct
            print(f"{scenario_id} {case_name}: {outcome.status} [reference]" + (f" ({sum(c['passed'] for c in result['checks'])}/{len(result['checks'])} checks)" if result else ""))
            if result and not valid:
                print("  Detected: " + ", ".join(c["name"] for c in result["checks"] if not c["passed"]))
            if outcome.error:
                print("  " + outcome.error["message"])
            cases.append({"scenario_id": scenario_id, "case": case_name, "backend_type": "reference", "injected_fault": fault,
                          "expected_status": "PASS" if valid else "FAIL", "status": outcome.status, "expectation_met": correct,
                          "required_failure_checks": sorted(required_failures),
                          "result": result, "error": outcome.error, "human_review": "not_reviewed"})
    summary = {"phase": 3, "backend_type": "reference", "model_execution_mode": "deterministic_reference",
               "teammate_modules_integrated": False,
               "selection": args.scenario, "cases": cases, "all_expectations_met": bool(verified), "human_review": "not_reviewed"}
    filename = "summary.json" if args.scenario == "all" else f"summary_{args.scenario}.json"
    write_json(args.output_dir / filename, summary)
    print(f"Summary: {len(ids)} valid passes and {len(ids)} injected failures expected; {'confirmed' if verified else 'unexpected outcomes'}. No physical actions executed.")
    print(f"Artifacts: {args.output_dir}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
