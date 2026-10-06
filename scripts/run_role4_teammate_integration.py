"""Fresh local real-code/scripted-LLM cases, with separately labelled controls."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from evaluation.role4.integration.offline import offline_guard
from evaluation.role4.logger import write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--dependency-path", type=Path, help="Existing compatible package directory only")
    args = parser.parse_args(argv)
    if args.dependency_path:
        if not args.dependency_path.is_dir():
            parser.error("Dependency directory unavailable")
        sys.path.append(str(args.dependency_path.resolve()))
    output = args.output_dir or ROOT / "evaluation/logs/role4/teammate_integration" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    with offline_guard() as blocked:
        from evaluation.role4.integration.teammate_runner import CONTROLS, run_teammate_case, verify_artifacts
        cases = [(s, "valid") for s in ("S01", "S02", "S03", "S07", "S08")]
        if args.controls:
            cases += [("S07" if c == "unavailable_evidence" else "S08" if c == "movement_attempt" else "S01", c)
                      for c in CONTROLS if c != "valid"]
        records = []
        for scenario, control in cases:
            record = run_teammate_case(scenario, output / f"{scenario}_{control}", control)
            records.append({k: record[k] for k in ("run_id", "scenario_id", "control", "labels", "evaluation", "expectation_met", "expected_failures", "pending_checks")})
            print(record["run_id"], "PASS" if record["evaluation"]["passed"] else "FAIL", "expectation_met=" + str(record["expectation_met"]))
        summary = {"cases": records, "all_expectations_met": all(r["expectation_met"] for r in records),
                   "blocked_network_attempts": len(blocked), "hosted_calls": 0,
                   "human_semantic_review": "pending", "hosted_reliability": "not_measured"}
        summary["artifact_verification"] = verify_artifacts(output)
        write_json(output / "summary.json", summary)
    print("Artifacts:", output)
    return 0 if summary["all_expectations_met"] and not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
