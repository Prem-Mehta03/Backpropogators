"""Gate check: the real model asks for read_lidar, our code runs it, the model answers.

Run from the repo root:  python -m scripts.run_lidar_tool_call
Uses Asvin's real sensor function once sensorimotor/sensors.py exists, otherwise the
placeholder stub. This script is the only place that wires two layers together.
"""

from __future__ import annotations

import json
import logging

from dotenv import load_dotenv

from procedural.llm_client import LLMClient, LLMClientError
from procedural.single_tool_call import run_single_tool_call

try:
    from sensorimotor.sensors import read_lidar  # Asvin's real API

    SENSOR_SOURCE = "sensorimotor.sensors"
except ImportError:
    from sensorimotor.stub import read_lidar  # placeholder until Asvin publishes

    SENSOR_SOURCE = "sensorimotor.stub (placeholder)"

QUESTION = "What does your front LiDAR currently read?"


def main() -> int:
    """Run the question and print tool calls plus the answer. Returns 0 only if a tool ran."""
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    print(f"sensor source: {SENSOR_SOURCE}")
    try:
        out = run_single_tool_call(LLMClient(), QUESTION, {"read_lidar": read_lidar})
    except LLMClientError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(json.dumps({"tool_calls": out.tool_calls, "answer": out.answer}, indent=2))
    return 0 if out.tool_was_called else 1


if __name__ == "__main__":
    raise SystemExit(main())
