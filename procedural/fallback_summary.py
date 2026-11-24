"""Fallback answer: a plain summary built from the tool log, with no model text in it.

Used when the model's own answer keeps failing the claim check (agent.py gives it
MAX_CLAIM_REFUSALS retries). The summary lists what memory returned, what the sensors read, what
this run wrote and where those sources disagree. It never decides between them and never names
a belief id the tools did not return, so it passes the claim check itself.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from contracts.sensor_evidence import reading_claim
from procedural.claims import MOVE_TOOLS, effective_statuses, failed_writes
from procedural.certainty import weak_or_disputed_reason
from procedural.update_guard import sensor_readings

MEMORY_READ_TOOLS = (
    "query_belief",
    "get_belief_history",
    "detect_conflict",
    "update_belief",
    "downgrade_belief",
)
LIVE_BELIEF_STATUSES = ("active", "disputed")
INTRO = (
    "Summary built from the tool results (my own answer did not pass the claim check)."
)
CLOSING = "This summary reports what each source said and does not choose between them."


def _belief_items(data: Any) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    return [
        i
        for i in items
        if isinstance(i, dict) and isinstance(i.get("belief_id"), str) and "object" in i
    ]


def stored_beliefs(tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Beliefs returned by memory tools in this run; the latest copy of each id wins."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in tool_log:
        result = entry["result"]
        if entry["tool"] in MEMORY_READ_TOOLS and result["ok"]:
            for belief in _belief_items(result["data"]):
                latest[belief["belief_id"]] = belief
    statuses = effective_statuses(
        tool_log
    )  # a copy written earlier may be superseded now
    return [{**latest[key], "status": statuses[key]} for key in sorted(latest)]


def _describe_belief(b: dict[str, Any]) -> str:
    return (
        f"- {b['belief_id']}: {b['subject']} {b['predicate']} = {b['object']} "
        f"(source {b['source']}, perspective {b['perspective']}, "
        f"confidence {b['confidence']}, status {b['status']}, time {b['timestamp']})"
    )


def _reading_value(reading: dict[str, Any]) -> str:
    value = reading.get("value")
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    unit = reading.get("unit")
    return f"{value} {unit}" if unit else str(value)


def _describe_reading(r: dict[str, Any]) -> str:
    return (
        f"- {r['sensor']}: {_reading_value(r)} (status {r['status']}, "
        f"confidence {r['confidence']}, time {r['timestamp']})"
    )


def _disagreements(
    beliefs: list[dict[str, Any]], readings: dict[str, dict[str, Any]]
) -> list[str]:
    """One line per (subject, predicate) where current beliefs and readings differ in value."""
    claims: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for b in beliefs:
        if b["status"] in LIVE_BELIEF_STATUSES:
            claims[(b["subject"], b["predicate"])].append(
                (f"{b['belief_id']} ({b['perspective']})", str(b["object"]))
            )
    for name, reading in sorted(readings.items()):
        observed = reading_claim(reading)
        if observed is not None:
            subject, predicate, value = observed
            if any(  # memory already holds this very reading as a belief: list it once
                b["status"] in LIVE_BELIEF_STATUSES
                and b["source"] == name
                and (b["subject"], b["predicate"], str(b["object"]))
                == (subject, predicate, value)
                for b in beliefs
            ):
                continue
            claims[(subject, predicate)].append((f"{name} (live reading)", value))
    lines = []
    for (subject, predicate), sources in sorted(claims.items()):
        if len({value for _, value in sources}) > 1:
            said = "; ".join(f"{label} says {value}" for label, value in sources)
            lines.append(f"- {subject} {predicate}: {said}")
    return lines


def _writes(tool_log: list[dict[str, Any]]) -> list[str]:
    statuses = effective_statuses(tool_log)  # the copy in a write result goes stale
    lines = []
    for entry in tool_log:
        if entry["tool"] not in ("downgrade_belief", "update_belief"):
            continue
        result = entry["result"]
        if result["ok"] and isinstance(result["data"], dict):
            b = result["data"]
            lines.append(
                f"- {entry['tool']} wrote {b['belief_id']}: {b['subject']} {b['predicate']} = "
                f"{b['object']} (confidence {b['confidence']}, "
                f"status {statuses.get(b['belief_id'], b['status'])})"
            )
        elif not result["ok"]:
            lines.append(f"- {entry['tool']} failed: {result['error']['message']}")
    return lines


def _actions(tool_log: list[dict[str, Any]]) -> list[str]:
    """One line per move the robot made or that the recheck before action cancelled."""
    lines = []
    for entry in tool_log:
        if entry["tool"] not in MOVE_TOOLS:
            continue
        distance = entry["args"].get("distance_cm")
        result = entry["result"]
        if result["ok"]:
            lines.append(f"- {entry['tool']} requested {distance} cm. Action result: {_reading_value(result['data'])}.")
        elif entry.get("guard", {}).get("recheck", {}).get("passed") is False:
            lines.append(
                f"- {entry['tool']} {distance} cm: cancelled, the robot did not move "
                f"({result['error']['message']})"
            )
        else:
            lines.append(f"- {entry['tool']} requested {distance} cm. The tool reported an error: "
                         f"{result['error']['message']}")
    return lines


def build_fallback_summary(question: str, tool_log: list[dict[str, Any]]) -> str:
    """Build the fallback answer from the tool log alone.

    Inputs: the question (kept for the signature; the text does not depend on it) and the run's
    tool log (state.tool_log). Output: plain text with stored evidence, observed evidence,
    memory writes and disagreements. Deterministic: the same log gives the same text.
    """
    beliefs = stored_beliefs(tool_log)
    readings = sensor_readings(tool_log)
    lines = [INTRO, "", "Stored evidence:"]
    lines += [_describe_belief(b) for b in beliefs] or ["- none"]
    lines += ["", "Observed evidence:"]
    lines += [_describe_reading(r) for _, r in sorted(readings.items())] or ["- none"]
    lines += ["", "Memory writes in this run:"]
    writes = _writes(tool_log)
    if writes:
        lines += writes
        if failed_writes(tool_log):
            lines.append("Memory was only partly updated. The results above show which write succeeded and which failed.")
    else:
        lines.append("- none: I made no memory writes in this run.")
    actions = _actions(tool_log)
    if actions:
        lines += ["", "Moves in this run:"] + actions
    usable_readings = [reading for reading in readings.values() if reading_claim(reading) is not None]
    if not beliefs and not usable_readings:
        lines += ["", "Evidence is missing: memory and the sensors returned nothing."]
    else:
        if not beliefs:
            lines += ["", "No stored belief was returned. This summary uses the observations that were available."]
        if not usable_readings:
            lines += ["", "No usable sensor reading verified the stored evidence."]
        conflicts = _disagreements(beliefs, readings)
        if conflicts:
            lines += ["", "Sources that disagree:"] + conflicts
        elif beliefs and usable_readings and weak_or_disputed_reason(tool_log) is None:
            lines += ["", "No disagreement between the sources above."]
    weak = weak_or_disputed_reason(tool_log)
    if weak is not None:
        lines += [
            "",
            f"The evidence is weak or conflicting: {weak}. I cannot confirm the state of the "
            "route. Please read the sensors again to get more evidence.",
        ]
    if any(b["source"] is None for b in beliefs):
        lines += ["", "At least one stored source is unknown. That claim cannot verify the world on its own."]
    lines += ["", CLOSING]
    return "\n".join(lines)
