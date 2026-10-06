"""STUB of Vyom's memory API. Returns fixed, valid contract JSON (Guidelines 4.2, 4.4, 4.5).

Fixtures: path_A/status is "clear" from default_map (confidence 1.0, historical) and
box_01/color has a user belief "red" and a third-party belief "blue" from bot_02.
Replace with the real memory functions; signatures and envelopes stay the same.
Placeholder owned by Vyom's real code: do not commit.
"""

from __future__ import annotations

from typing import Any

from contracts.models import Belief, ToolResult

FIXED_TS = "2026-10-03T09:15:00Z"


def _belief(
    belief_id: str,
    subject: str,
    predicate: str,
    obj: Any,
    source: str | None,
    confidence: float,
    perspective: str,
    status: str = "active",
    supersedes: str | None = None,
) -> dict[str, Any]:
    return Belief(
        schema_version="1.0",
        belief_id=belief_id,
        subject=subject,
        predicate=predicate,
        object=obj,
        source=source,
        confidence=confidence,
        timestamp=FIXED_TS,
        perspective=perspective,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        valid_from=FIXED_TS,
        valid_to=None,
        supersedes=supersedes,
    ).model_dump()


def _fixtures() -> list[dict[str, Any]]:
    return [
        _belief(
            "b_000123", "path_A", "status", "clear", "default_map", 1.0, "historical"
        ),
        _belief("b_000201", "box_01", "color", "red", "user", 0.9, "user"),
        _belief("b_000202", "box_01", "color", "blue", "bot_02", 0.8, "third_party"),
    ]


def _ok(tool: str, data: Any) -> dict[str, Any]:
    return ToolResult(
        schema_version="1.0",
        tool=tool,
        ok=True,
        data=data,
        error=None,
        timestamp=FIXED_TS,
    ).model_dump()


def _fail(tool: str, code: str, message: str) -> dict[str, Any]:
    return ToolResult.model_validate(
        {
            "schema_version": "1.0",
            "tool": tool,
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message, "retryable": False},
            "timestamp": FIXED_TS,
        }
    ).model_dump()


def query_belief(
    subject: str, predicate: str | None = None, perspective: str | None = None
) -> dict[str, Any]:
    """List beliefs about a subject. Error codes: NOT_FOUND when nothing matches."""
    found = [
        b
        for b in _fixtures()
        if b["subject"] == subject
        and (predicate is None or b["predicate"] == predicate)
        and (perspective is None or b["perspective"] == perspective)
    ]
    if not found:
        return _fail(
            "query_belief", "NOT_FOUND", f"No belief for {subject}/{predicate}"
        )
    return _ok("query_belief", found)


def get_belief_history(subject: str, predicate: str | None = None) -> dict[str, Any]:
    """Beliefs about a subject, oldest first. Error codes: NOT_FOUND when nothing matches."""
    found = [
        b
        for b in _fixtures()
        if b["subject"] == subject
        and (predicate is None or b["predicate"] == predicate)
    ]
    if not found:
        return _fail(
            "get_belief_history", "NOT_FOUND", f"No history for {subject}/{predicate}"
        )
    return _ok("get_belief_history", found)


def update_belief(
    subject: str,
    predicate: str,
    object: Any,
    source: str,
    confidence: float,
    perspective: str,
    reason: str,
) -> dict[str, Any]:
    """Store a new belief; it supersedes b_000123 when it is about path_A/status."""
    supersedes = "b_000123" if (subject, predicate) == ("path_A", "status") else None
    new = _belief(
        "b_000124",
        subject,
        predicate,
        object,
        source,
        confidence,
        perspective,
        "active",
        supersedes,
    )
    return _ok("update_belief", new)


def downgrade_belief(
    belief_id: str, new_confidence: float, reason: str
) -> dict[str, Any]:
    """Lower a belief's confidence. Error codes: NOT_FOUND for an unknown belief id."""
    for belief in _fixtures():
        if belief["belief_id"] == belief_id:
            belief["confidence"] = new_confidence
            return _ok("downgrade_belief", belief)
    return _fail("downgrade_belief", "NOT_FOUND", f"No belief with id {belief_id}")


def detect_conflict(subject: str, predicate: str) -> dict[str, Any]:
    """List conflicting beliefs. The stub memory holds no conflicting pair, so data is []."""
    return _ok("detect_conflict", [])
