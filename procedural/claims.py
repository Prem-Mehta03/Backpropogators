"""Claim check: an answer may only claim memory writes that really happened in this run.

A model can write "I downgraded b_000002 to 0.4" without ever calling downgrade_belief. The
tool log is the ground truth, so this module compares the answer text with it. Two things are
checked: a claimed downgrade or update needs a successful call of that tool, and every belief id
named in the answer must appear in this run's tool log. The reverse also holds: every belief
the run really wrote must be named in the answer. Sentences that deny a write ("I made no
writes", "left unchanged") are not claims and are skipped.
"""

from __future__ import annotations

import json
import re
from typing import Any

BELIEF_ID = re.compile(r"\bb_\d{3,}\b")
DOWNGRADE_WORDS = re.compile(r"\bdowngrad(?:e|ed|ing)\b", re.IGNORECASE)
UPDATE_WORDS = re.compile(
    r"\b(?:recorded|updated|added|created|wrote|written|saved)\b.*\b(?:belief|beliefs|memory|graph)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(
    r"\b(?:not|never|nothing|none|without|unchanged|neither|nor|no\s+(?:writes?|updates?|changes?))\b"
    r"|n't",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
LEADING_ANSWER_WORD = re.compile(r"^\W*(?:yes|no)\b[,.:]?\s*", re.IGNORECASE)


def _succeeded(tool_log: list[dict[str, Any]], tool: str) -> bool:
    return any(e["tool"] == tool and e["result"]["ok"] for e in tool_log)


def written_belief_ids(tool_log: list[dict[str, Any]]) -> list[str]:
    """Ids of the beliefs this run really wrote (successful downgrade or update), in order."""
    ids: list[str] = []
    for entry in tool_log:
        result = entry["result"]
        if entry["tool"] in ("downgrade_belief", "update_belief") and result["ok"]:
            data = result["data"]
            if isinstance(data, dict) and isinstance(data.get("belief_id"), str):
                ids.append(data["belief_id"])
    return ids


def _is_claim(sentence: str, pattern: re.Pattern[str]) -> bool:
    body = LEADING_ANSWER_WORD.sub("", sentence, count=1)
    return bool(pattern.search(body)) and not NEGATION.search(body)


def unbacked_write_claims(
    answer: str, tool_log: list[dict[str, Any]], require_written_ids: bool = False
) -> list[str]:
    """List the claims in `answer` that the tool log does not support; [] when all are backed.

    Inputs: the answer text, the run's tool log (state.tool_log), and require_written_ids: when
    True, every belief the run really wrote must also be named in the answer (used for live
    runs; scripted test answers are free text and do not have to name ids). Output: one short
    description per problem, in a fixed order (downgrade, update, unreported writes, unknown ids).
    """
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(answer) if s.strip()]
    problems: list[str] = []
    if not _succeeded(tool_log, "downgrade_belief") and any(
        _is_claim(s, DOWNGRADE_WORDS) for s in sentences
    ):
        problems.append("you claim a downgrade, but no downgrade_belief call succeeded")
    if not _succeeded(tool_log, "update_belief") and any(
        _is_claim(s, UPDATE_WORDS) for s in sentences
    ):
        problems.append(
            "you claim a memory update, but no update_belief call succeeded"
        )
    written = written_belief_ids(tool_log)
    named = set(BELIEF_ID.findall(answer))
    unreported = [b for b in written if b not in named] if require_written_ids else []
    if unreported:
        problems.append(
            "you wrote belief(s) "
            + ", ".join(unreported)
            + " but your answer does not name "
            "them; name every belief you downgraded or recorded"
        )
    seen = set(BELIEF_ID.findall(json.dumps(tool_log)))
    unknown = sorted(set(BELIEF_ID.findall(answer)) - seen)
    if unknown:
        problems.append("you name belief ids no tool returned: " + ", ".join(unknown))
    return problems
