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
from dataclasses import dataclass
from typing import Any

from contracts.models import Belief, SensorReading

SENSOR_TOOLS = ("read_lidar", "read_camera", "get_position")
DISTANCE_TOOLS = ("read_lidar", "read_ultrasonic")

# Each inner tuple is one requirement: any one tool from it is enough.
DEFAULT_REQUIRED_EVIDENCE: tuple[tuple[str, ...], ...] = (
    ("query_belief",),
    SENSOR_TOOLS,
)

# Error codes a layer returns when it looked and found nothing: still an attempt at evidence.
EVIDENCE_ATTEMPT_CODES = ("NOT_FOUND", "SENSOR_UNAVAILABLE", "STORAGE_ERROR")


@dataclass(frozen=True)
class EvidenceCapability:
    """The property and sensor that the caller has selected for a scoped question."""

    subject: str
    predicate: str
    tool: str
    label: str
    arguments: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not (self.tool.startswith("read_") or self.tool == "get_position"):
            raise ValueError("An evidence capability must name a read-only sensor tool")

    def permits(self, tool: str, args: dict[str, Any]) -> bool:
        """Check that the proposed read is for the caller-selected capability."""
        if tool == "query_belief":
            return (
                args.get("subject") == self.subject
                and args.get("predicate") in (None, self.predicate)
                and args.get("perspective") is None
            )
        return tool == self.tool and args == dict(self.arguments)


def capability_evidence(
    tool_log: list[dict[str, Any]], capability: EvidenceCapability, registered: Sequence[str]
) -> tuple[list[str], str | None]:
    """Report scoped evidence still needed, or furnish a value-free abstention when justified."""
    beliefs = []
    queried = False
    for entry in tool_log:
        args, result = entry["args"], entry["result"]
        if entry["tool"] != "query_belief" or not capability.permits(entry["tool"], args):
            continue
        if not result["ok"]:
            queried |= result["error"]["code"] == "NOT_FOUND"
            continue
        if isinstance(result["data"], list):
            try:
                matches = [Belief.model_validate(row) for row in result["data"]]
            except ValueError:
                continue
            if any(
                b.subject != capability.subject
                or (args.get("predicate") is not None and b.predicate != capability.predicate)
                for b in matches
            ):
                continue
            queried = True
            beliefs.extend(b for b in matches
                           if (b.subject, b.predicate) == (capability.subject, capability.predicate))
    if not queried:
        return [f"query_belief for {capability.subject}/{capability.predicate}"], None

    if capability.tool not in registered:
        explanation = "No matching sensor is connected."
    else:
        unavailable = False
        for entry in tool_log:
            if entry["tool"] != capability.tool or not capability.permits(entry["tool"], entry["args"]):
                continue
            result = entry["result"]
            if not result["ok"]:
                unavailable |= result["error"]["code"] in ("NOT_FOUND", "SENSOR_UNAVAILABLE")
                continue
            try:
                reading = SensorReading.model_validate(result["data"])
            except ValueError:
                continue
            if reading.status in ("clear", "blocked"):
                return [], None
            unavailable |= reading.status == "unknown"
        if not unavailable:
            return [capability.tool], None
        explanation = "The matching sensor returned no usable evidence."

    if any(entry["tool"] in {"update_belief", "downgrade_belief", "move_forward", "move_backward", "turn"}
           for entry in tool_log):
        # A short abstention must not conceal a write or action, including a rejected request.
        return [f"{capability.tool} evidence after a write or action request"], None
    if any(b.source is None for b in beliefs):
        memory = "The matching stored claim has no recorded source."
    elif beliefs:
        memory = "The matching stored evidence alone does not verify this."
    else:
        memory = "Memory returned no matching claim."
    return [], f"I cannot verify the {capability.label}. {explanation} {memory}"


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
    tool_log: list[dict[str, Any]],
    required: Sequence[Sequence[str]],
    registered: Sequence[str] = (),
) -> list[str]:
    """List the requirements not yet met.

    Inputs: the tool log (state.tool_log), the requirement groups and the names of the tools
    registered in this run. Output: a description of each unmet requirement, in order; [] when
    all are met. With the default requirements, a question about a route (a path_* subject)
    also needs every registered distance sensor and get_belief_history for that subject.
    """
    queried = {
        str(entry["args"].get("subject", ""))
        for entry in tool_log if entry["tool"] == "query_belief"
    }
    route_query = any(s.startswith("path_") for s in queried)
    object_query = any(s.startswith("box_") for s in queried)
    attempted = set()
    for entry in tool_log:
        name = entry["tool"]
        front = (name != "read_lidar"
                 or entry["args"].get("direction", "front") == "front")
        about_route = name != "get_belief_history" or str(
            entry["args"].get("subject", "")
        ).startswith("path_")
        if evidence_attempted(entry) and (front or not route_query) and about_route:
            attempted.add(name)
        guard = entry.get("guard", {}).get("recheck", {})
        if guard.get("direction") == "front":
            attempted.update(
                item["tool"] for item in guard.get("reads", ()) if evidence_attempted(item)
            )
    if required == DEFAULT_REQUIRED_EVIDENCE:
        relevant = tuple((name,) for name in DISTANCE_TOOLS if route_query and name in registered)
        if route_query and "get_belief_history" in registered:
            # A superseded (stale) belief is invisible to query_belief, which returns only
            # current beliefs. History is the only way to see that an older entry was replaced
            # (T06, live 0/3: the model never saw the 2026-09-01 map and never called it stale).
            relevant += (("get_belief_history",),)
        if object_query and "read_camera" in registered:
            relevant += (("read_camera",),)
        if relevant:
            required = (("query_belief",), *relevant)
    return [describe_requirement(g) for g in required if not attempted.intersection(g)]
