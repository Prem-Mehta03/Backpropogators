"""Provenance guard for memory writes (a rule in code: the LLM never invents evidence).

Checks the model's downgrade_belief and update_belief calls against what actually happened in
this run, before they reach the memory layer:
- downgrade_belief: the belief id must have been returned by a memory tool earlier in this run
  (no invented ids) and the new confidence must be lower than the belief's current one.
- update_belief with perspective agent_sensor: the source must be a sensor that was read
  successfully in this run, and the confidence is taken from that reading, not from the model.
Everything else passes through to the normal argument validation unchanged. This module holds
no conflict-priority rules; those belong to declarative/conflicts.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from procedural.state import MEMORY_TOOLS

SENSOR_READ_TOOLS = ("read_lidar", "read_camera", "get_position")


@dataclass(frozen=True)
class GuardDecision:
    """Outcome of a check: the arguments to run, or an error message to show the model."""

    args: dict[str, Any]
    error: str | None = None
    overridden: dict[str, Any] = field(default_factory=dict)


def _belief_items(data: Any) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    return [i for i in items if isinstance(i, dict) and "belief_id" in i]


def known_belief_confidences(tool_log: list[dict[str, Any]]) -> dict[str, float]:
    """Belief id -> latest confidence, from successful memory results in this run."""
    known: dict[str, float] = {}
    for entry in tool_log:
        result = entry["result"]
        if entry["tool"] in (*MEMORY_TOOLS, "downgrade_belief") and result["ok"]:
            for belief in _belief_items(result["data"]):
                known[belief["belief_id"]] = belief["confidence"]
    return known


def sensor_readings(tool_log: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sensor name -> most recent successful reading in this run."""
    readings: dict[str, dict[str, Any]] = {}
    for entry in tool_log:
        result = entry["result"]
        if (
            entry["tool"] in SENSOR_READ_TOOLS
            and result["ok"]
            and isinstance(result["data"], dict)
        ):
            readings[result["data"]["sensor"]] = result["data"]
    return readings


def _check_downgrade(
    args: dict[str, Any], tool_log: list[dict[str, Any]]
) -> GuardDecision:
    belief_id, new_confidence = args.get("belief_id"), args.get("new_confidence")
    if not isinstance(belief_id, str) or not isinstance(new_confidence, (int, float)):
        return GuardDecision(args)  # malformed: normal validation reports it
    if isinstance(new_confidence, bool):
        return GuardDecision(args)  # malformed: normal validation reports it
    known = known_belief_confidences(tool_log)
    if belief_id not in known:
        return GuardDecision(
            args,
            f"belief_id {belief_id} was not returned by any memory lookup in this run. "
            "Call query_belief first and use a belief_id from its result.",
        )
    if new_confidence >= known[belief_id]:
        return GuardDecision(
            args,
            f"new_confidence must be lower than the current confidence {known[belief_id]}.",
        )
    return GuardDecision(args)


def _check_sensor_update(
    args: dict[str, Any], tool_log: list[dict[str, Any]]
) -> GuardDecision:
    source = args.get("source")
    if not isinstance(source, str):
        return GuardDecision(args)  # malformed: normal validation reports it
    readings = sensor_readings(tool_log)
    if source not in readings:
        return GuardDecision(
            args,
            f"source {source!r} is not a sensor read successfully in this run "
            f"(sensors read so far: {sorted(readings)}). Read the sensor first and use its name "
            "as the source. You cannot record an observation you have not made.",
        )
    confidence = readings[source]["confidence"]
    if args.get("confidence") == confidence:
        return GuardDecision(args)
    return GuardDecision(
        {**args, "confidence": confidence},
        overridden={
            "confidence": {"model_value": args.get("confidence"), "used": confidence}
        },
    )


def check_memory_call(
    name: str, args: dict[str, Any], tool_log: list[dict[str, Any]]
) -> GuardDecision:
    """Check one model-requested call against this run's history.

    Inputs: tool name, the model's arguments, the tool log so far.
    Output: GuardDecision. `error` set means refuse the call and tell the model why;
    `overridden` lists argument values the code replaced with values taken from evidence.
    """
    if name == "downgrade_belief":
        return _check_downgrade(args, tool_log)
    if name == "update_belief" and args.get("perspective") == "agent_sensor":
        return _check_sensor_update(args, tool_log)
    return GuardDecision(args)
