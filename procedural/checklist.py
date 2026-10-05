"""Evidence checklist: the agent may not give a final answer until it has looked.

Guidelines 5: "The agent must call query_belief and the relevant sensor tool before answering
an epistemic question. If either returns no data, it says that evidence is missing."
This is a rule in code. A requirement is a group of tool names; it is met when any tool in the
group was called and reached its layer. A NOT_FOUND or SENSOR_UNAVAILABLE reply still counts
(the agent looked and found nothing, which is what test 7 expects it to report). A call
rejected for bad arguments, or one that failed inside our own wrapper, does not count.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

SENSOR_TOOLS = ("read_lidar", "read_camera", "get_position")

# Each inner tuple is one requirement: any one tool from it is enough.
DEFAULT_REQUIRED_EVIDENCE: tuple[tuple[str, ...], ...] = (
    ("query_belief",),
    SENSOR_TOOLS,
)

# Error codes a layer returns when it looked and found nothing: still an attempt at evidence.
EVIDENCE_ATTEMPT_CODES = ("NOT_FOUND", "SENSOR_UNAVAILABLE", "STORAGE_ERROR")


def evidence_attempted(entry: dict[str, Any]) -> bool:
    """True if this tool-log entry reached its layer (ok, or a 'found nothing' error)."""
    result = entry["result"]
    if result["ok"]:
        return True
    return result["error"]["code"] in EVIDENCE_ATTEMPT_CODES


def describe_requirement(group: Sequence[str]) -> str:
    """Name a requirement for humans: 'query_belief' or 'one of read_lidar, read_camera'."""
    return group[0] if len(group) == 1 else "one of " + ", ".join(group)


def missing_evidence(
    tool_log: list[dict[str, Any]], required: Sequence[Sequence[str]]
) -> list[str]:
    """List the requirements not yet met.

    Inputs: the tool log (state.tool_log) and the requirement groups.
    Output: a description of each unmet requirement, in order; [] when all are met.
    """
    attempted = {entry["tool"] for entry in tool_log if evidence_attempted(entry)}
    return [describe_requirement(g) for g in required if not attempted.intersection(g)]
