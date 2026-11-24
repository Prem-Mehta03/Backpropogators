"""Final Guidelines 4.6 logs on the actual three layers, with optional hosted model runs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys

from evaluation.role4.integration.offline import offline_guard

ROOT = Path(__file__).resolve().parents[1]


def run_case(test_id: str, output: Path, *, run_id: str, live: bool = False, seed: int = 42) -> dict:
    """Run one fresh case and write a test log, event log and frame trace. Reject missing real tools."""
    from declarative import BeliefMemory
    from declarative.seed import seed_for
    from evaluation.logger import EvaluationLogger
    from evaluation.role4.logger import write_json
    from evaluation.stretch_checks import evaluate_case
    from evaluation.stretch_specs import CASES, DEMO, ScriptedModel
    from procedural.agent import run_agent
    from procedural.llm_client import LLMClient
    from procedural.prompts import PROMPT_VERSION
    from scripts.frame_recorder import FrameRecorder
    from scripts.tool_wiring import MEMORY_TOOLS
    from sensorimotor import create_sensorimotor
    from sensorimotor.world_view import export_frame

    if not run_id or any(c not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_" for c in run_id):
        raise ValueError("run_id must be a nonempty path-safe identifier")
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    case = DEMO if test_id == "B_APPROACH" else CASES[test_id]
    output = output / f"{test_id}__{run_id}"
    output.mkdir(parents=True, exist_ok=False)
    world = create_sensorimotor(case.scenario, seed)
    world.env.reset()
    logger = EvaluationLogger(output)
    memory_events = []

    def memory_event(kind: str, details: dict) -> None:
        memory_events.append(logger.log_event(run_id, kind, details))

    memory = BeliefMemory(clock=world.env.now_iso, event_callback=memory_event)
    try:
        seeds = seed_for("scenario_b_approach" if test_id == "B_APPROACH" else test_id, memory)
        if any(not r["ok"] for r in seeds):
            raise ValueError(f"Memory rejected a scenario seed for {test_id}")
        sensors = world.tool_registry()
        if not {"read_lidar", "read_camera", "move_forward"} <= sensors.keys():
            raise ValueError("Actual sensorimotor registry is incomplete")
        registry = {**{name: getattr(memory, name) for name in MEMORY_TOOLS}, **sensors}
        tool_sources = {name: f"{method.__module__}.{method.__qualname__}" for name, method in registry.items()}

        def snapshot() -> dict:
            return {"memory": memory.snapshot(), "environment": world.env.get_state()}

        before = snapshot()
        recorder = FrameRecorder(world.env, memory, export_frame=export_frame)
        recorder.capture_initial()
        observed = []

        def observe(step: int, tool: str, args: dict, result: dict, auto: bool) -> None:
            item = {"step": step, "tool": tool, "args": args, "result": result, "auto": auto}
            observed.append(item)
            recorder.on_step(step, tool, args, result, auto)
            logger.log_event(run_id, "tool_observation", item)

        llm = LLMClient(temperature=0.0, retry_temperature=0.0) if live else ScriptedModel(test_id)
        subjects = {"path_A": "the route ahead", "box_01": "the box in the room"}
        if test_id == "T07":
            subjects["box_99"] = "the entity asked about; its existence is unknown"
        agent = asdict(run_agent(case.question, llm, registry, known_subjects=subjects,
                                 require_written_ids=test_id in {"T01", "T02"}, on_step=observe))
        after = snapshot()
        checks = evaluate_case(test_id, case, before, after, agent, observed, memory_events, recorder.frames)
        failures = [c for c in checks if not c["passed"]]
        mode = "live" if live else "scripted_llm"
        labels = {"execution": mode, "environment": "simulated",
                  "layers": {"declarative": "actual", "procedural": "actual", "sensorimotor": "actual"}}
        model = llm.model if live else "scripted_llm"
        trace_file = f"agent_run_{run_id}.json"
        trace = {
            **agent, "test_id": test_id, "run_id": run_id, "scenario": case.scenario, "seed": seed,
            "model": model, "model_switched_from": getattr(llm, "switched_from", None),
            "prompt_version": PROMPT_VERSION, "labels": labels, "frames": recorder.frames,
            "observed_tools": observed, "tool_sources": tool_sources,
            "state_before": before, "state_after": after, "memory_events": memory_events,
        }
        write_json(output / trace_file, trace)
        record = {
            "question": case.question, "state_before": before, "tool_calls": observed, "state_after": after,
            "answer": agent["answer"], "expected": case.expected, "checks": checks,
            "result": "FAIL" if failures else "PASS", "model": model, "trace_file": trace_file,
            "answer_source": agent["answer_source"], "labels": labels, "agent_error": agent["error"],
            "failure_layers": sorted({c["layer"] for c in failures}), "scenario": case.scenario,
            "started_utc": started_at,
        }
        logger.write_test_log(test_id, run_id, record)
        return record
    finally:
        memory.close()


def main(argv: list[str] | None = None) -> int:
    """Run selected tests or the box-approach demo. Fake mode blocks network and dotenv."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--tests", default=",".join(f"T{i:02}" for i in range(1, 11)))
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 51), metavar="1-50")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/logs/final")
    parser.add_argument("--dependency-path", type=Path, help="Append an existing compatible package directory.")
    args = parser.parse_args(argv)
    if args.dependency_path:
        if not args.dependency_path.is_dir():
            parser.error("Dependency directory is unavailable")
        sys.path.append(str(args.dependency_path.resolve()))
    choices = {f"T{i:02}" for i in range(1, 11)} | {"B_APPROACH"}
    selected = [value.strip().upper() for value in args.tests.split(",")]
    if not set(selected) <= choices or len(set(selected)) != len(selected):
        parser.error("Choose a comma-separated list of distinct T01–T10 or B_APPROACH")
    if args.live:
        from importlib.util import find_spec
        from dotenv import load_dotenv
        if find_spec("openai") is None:
            parser.error("--live requires the existing OpenAI Python dependency")
        load_dotenv(ROOT / ".env")
    block = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    logging.basicConfig(level=logging.WARNING)

    def execute() -> bool:
        all_passed = True
        for test_id in selected:
            for repeat in range(1, args.repeats + 1):
                result = run_case(test_id, args.output_dir, run_id=f"{block}-{repeat:02}",
                                  live=args.live, seed=args.seed)
                print(f"{test_id} {repeat}/{args.repeats}: {result['result']} ({result['model']})")
                for check in result["checks"]:
                    if not check["passed"]:
                        print(f"  {check['layer']}: {check['name']} — {check['detail']}")
                all_passed &= result["result"] == "PASS"
        return all_passed

    if args.live:
        return int(not execute())
    with offline_guard() as blocked:
        passed = execute()
    print(f"Blocked network attempts: {len(blocked)}")
    return int(not passed or bool(blocked))


if __name__ == "__main__":
    raise SystemExit(main())
