"""Turn actual Guidelines logs into a scoped machine-readable summary and report table."""

import argparse
from collections import Counter
import json
from pathlib import Path

from evaluation.logger import load_test_log
from evaluation.stretch_specs import CASES


def summarize(logs: list[Path]) -> dict:
    """Verify final test receipts and return separate scripted and live statistics."""
    runs = {"scripted_llm": {tid: [] for tid in CASES}, "live": {tid: [] for tid in CASES}}
    seen = set()
    for folder in logs:
        if not folder.is_dir():
            raise ValueError(f"Evidence directory unavailable: {folder}")
        for path in sorted(folder.rglob("T*__*.json")):
            log = load_test_log(path)
            mode = log.get("labels", {}).get("execution")
            test_id = log["test_id"]
            if test_id not in CASES or mode not in runs:
                raise ValueError(f"Final evidence lacks a known case or labelled execution mode: {path}")
            if (log["model"] == "scripted_llm") != (mode == "scripted_llm"):
                raise ValueError(f"Model label conflicts with execution mode: {path}")
            if any(log["labels"].get("layers", {}).get(layer) != "actual"
                   for layer in ("declarative", "procedural", "sensorimotor")):
                raise ValueError(f"Final results require actual implementations: {path}")
            identity = (test_id, log["run_id"])
            if identity in seen:
                raise ValueError(f"Duplicate run ID for {test_id}: {log['run_id']}")
            seen.add(identity)
            failing = [c for c in log["checks"] if not c["passed"]]
            if not log["checks"] or log["result"] != ("FAIL" if failing else "PASS"):
                raise ValueError(f"Log verdict is inconsistent with checks: {path}")
            trace_file = log["trace_file"]
            if Path(trace_file).name != trace_file:
                raise ValueError(f"Trace path must point beside the test log: {path}")
            trace = json.loads(path.with_name(trace_file).read_text(encoding="utf-8"))
            pairs = {"question": "question", "answer": "answer", "observed_tools": "tool_calls",
                     "state_before": "state_before", "state_after": "state_after",
                     "model": "model", "answer_source": "answer_source", "labels": "labels"}
            if (trace.get("run_id") != log["run_id"] or trace.get("test_id") != test_id
                    or any(trace.get(a) != log.get(b) for a, b in pairs.items())):
                raise ValueError(f"Trace and test log disagree: {path}")
            runs[mode][test_id].append({
                "run_id": log["run_id"], "result": log["result"], "model": log["model"],
                "answer_source": log["answer_source"],
                "failing_layers": sorted({c["layer"] for c in failing}),
            })

    def metrics(items: list[dict]) -> dict:
        return {
            "runs": len(items), "passes": sum(item["result"] == "PASS" for item in items),
            "fallback_count": sum(item["answer_source"] == "fallback_summary" for item in items),
            "models": sorted({item["model"] for item in items}),
            "failing_layers": dict(sorted(Counter(layer for item in items for layer in item["failing_layers"]).items())),
        }

    return {"tests": {tid: {mode: {**metrics(cases[tid]), "receipts": cases[tid]} for mode, cases in runs.items()}
                      for tid in CASES},
            "totals": {mode: metrics([item for cases in test_runs.values() for item in cases])
                       for mode, test_runs in runs.items()},
            "live_target_per_test": 3}


def results_table(summary: dict) -> str:
    """Render measured denominators, registered model names and failing layers."""
    lines = ["# Final Evaluation Results", "",
             "| Test | Offline passes | Live passes | Live fallback | Live models | Failing layers |",
             "| --- | ---: | ---: | ---: | --- | --- |"]
    for tid, results in summary["tests"].items():
        offline, live = results["scripted_llm"], results["live"]
        offline_rate = f"{offline['passes']}/{offline['runs']}" if offline["runs"] else "Not run"
        live_rate = f"{live['passes']}/{live['runs']}" if live["runs"] else "Not run"
        layers = sorted(offline["failing_layers"].keys() | live["failing_layers"].keys())
        lines.append(f"| {tid} | {offline_rate} | {live_rate} | {live['fallback_count'] if live['runs'] else '—'} "
                     f"| {', '.join(live['models']) or '—'} | {', '.join(layers) or '—'} |")
    lines.extend(["", "Each denominator counts the logs supplied for that mode. The target is three live runs per test.",
                  "Historical demo runs and unlabelled traces are excluded. A fallback counts as a pass only when all checks pass."])
    return "\n".join(lines) + "\n"


def main() -> int:
    """Generate summary.json and results_table.md. Exit nonzero for missing or inconsistent evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, action="append")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results"))
    args = parser.parse_args()
    try:
        summary = summarize(args.logs or [Path("evaluation/logs/final")])
        if not any(stats["runs"] for stats in summary["totals"].values()):
            raise ValueError("No final test logs were found")
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "results_table.md").write_text(results_table(summary), encoding="utf-8")
    print(f"Results: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
