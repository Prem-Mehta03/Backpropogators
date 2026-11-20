"""Run the final Role 4 evidence suite offline on fresh simulated state."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from evaluation.role4.integration.offline import offline_guard


def main(argv: list[str] | None = None) -> int:
    """Run the suite, or return nonzero for an evidence error or a requested strict gate failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=5, choices=range(1, 51), metavar="1-50")
    parser.add_argument("--seed", type=int, default=42, help="Fixed simulation seed for every repeat")
    parser.add_argument("--scenario", action="append", choices=[f"S{i:02}" for i in range(1, 11)],
                        help="Choose a case. Repeat to choose several.")
    parser.add_argument("--output-dir", type=Path, help="New directory for evidence; existing runs are preserved")
    parser.add_argument("--dependency-path", type=Path, help="Optional existing compatible package directory")
    parser.add_argument("--no-controls", action="store_true", help="Run only the normal cases")
    parser.add_argument("--show-cases", action="store_true", help="Print canonical evidence for the first trial")
    parser.add_argument("--strict", action="store_true",
                        help="Also fail on canonical behavior gaps exposed by selected cases or controls")
    args = parser.parse_args(argv)
    if args.scenario and len(args.scenario) != len(set(args.scenario)):
        parser.error("Select each scenario at most once.")
    if args.dependency_path:
        if not args.dependency_path.is_dir():
            parser.error("Dependency directory unavailable.")
        sys.path.append(str(args.dependency_path.resolve()))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (args.output_dir or ROOT / "evaluation/logs/role4/final" / stamp).resolve()
    if output.exists():
        parser.error(f"Evidence directory already exists: {output}")

    with offline_guard() as blocked:
        from evaluation.role4.final_suite import CASES, run_suite

        summary = run_suite(output, trials=args.trials, seed=args.seed, scenarios=tuple(args.scenario or CASES),
                            controls=not args.no_controls, show_cases=args.show_cases, blocked=blocked)

    for scope, counts in summary["counts"].items():
        print(f"{scope}: {counts['passes']}/{counts['runs']} PASS; "
              f"{counts['expected_outcomes']}/{counts['runs']} matched expectation")
    print(f"Validated boundary samples: {summary['conformance']['samples']} across "
          f"{summary['conformance']['tools']} tools; all passed: {summary['conformance']['passed']}")
    print(f"Canonical behavior gaps: {len(summary['canonical_behavior_gaps'])}")
    print(f"Evidence: {output}")
    for outcome in summary["unexpected_outcomes"]:
        print(f"Unexpected outcome: {outcome}", file=sys.stderr)
    for case in summary["unstable_case_groups"]:
        print(f"Repeatability check failed: {case}", file=sys.stderr)
    if (blocked or not summary["conformance"]["passed"] or summary["unexpected_outcomes"]
            or summary["unstable_case_groups"]):
        return 1
    return 2 if args.strict and summary["canonical_behavior_gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
