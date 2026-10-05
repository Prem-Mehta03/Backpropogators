"""Ask the agent one question with the real model and save a JSON log of the run.

Run from the repo root:
    python -m scripts.ask_agent
    python -m scripts.ask_agent "Is your route clear? Justify your answer."
    python -m scripts.ask_agent --stubs-only --max-steps 6 "What does your front LiDAR read?"

Tools come from scripts/tool_wiring.py (real layers when they exist, stubs otherwise).
The log goes to evaluation/logs/ and is what you read when listing failures per layer.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from procedural.agent import DEFAULT_MAX_STEPS, run_agent
from procedural.llm_client import LLMClient, LLMClientError
from procedural.state import subjects_outside
from scripts.tool_wiring import build_tool_registry

# Entity ids that exist in memory, with a plain description so the model can map the words in a
# question ("route") to the right id (path_A). This stands in for the scenario config; replace
# it with the real list from Asvin's scenario config or Vyom's memory when they are published.
DEFAULT_SUBJECTS: dict[str, str] = {
    "path_A": "the path ahead of the robot (the route the robot would take)",
    "box_01": "the box the user is asking about",
    "robot": "this robot itself",
}

DEFAULT_QUESTION = "Is your route clear? Justify your response by inspecting your internal system layers."


def main(argv: list[str] | None = None) -> int:
    """Run one question. Returns 0 if the agent gave a final answer, otherwise 1."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--stubs-only", action="store_true", help="ignore real layers")
    parser.add_argument(
        "--no-entity-list",
        action="store_true",
        help="do not tell the model which entity ids exist (reproduces the 'route' failure)",
    )
    parser.add_argument("--log-dir", default="evaluation/logs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    registry, sources = build_tool_registry(use_real=not args.stubs_only)
    try:
        llm = LLMClient()
    except LLMClientError as exc:
        print(f"FAILED: {exc}")
        return 1

    subjects = None if args.no_entity_list else DEFAULT_SUBJECTS
    result = run_agent(
        args.question, llm, registry, max_steps=args.max_steps, known_subjects=subjects
    )
    unknown = subjects_outside(result.tool_calls, DEFAULT_SUBJECTS)

    now = datetime.now(timezone.utc)
    log = {
        "run_id": now.strftime("%Y-%m-%dT%H:%M:%SZ") + "-1",
        "model": llm.model,
        "question": result.question,
        "tool_sources": sources,
        "known_subjects": subjects,
        "unknown_subjects_used": unknown,
        "tool_calls": result.tool_calls,
        "model_calls": result.model_calls,
        "evidence_nudges": result.evidence_nudges,
        "answer": result.answer,
        "answer_normalized": result.answer_normalized,
        "error": result.error,
    }
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"agent_run_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"tools called: {[c['tool'] for c in result.tool_calls]}")
    print(f"model calls: {result.model_calls}")
    print(f"evidence nudges: {result.evidence_nudges}")
    print(f"unknown subjects used: {unknown}")
    print(f"error: {result.error}")
    print(f"answer:\n{result.answer}")
    print(f"log saved: {path}")
    return 0 if result.finished else 1


if __name__ == "__main__":
    raise SystemExit(main())
