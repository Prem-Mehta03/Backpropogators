"""Claim check: an answer may only claim memory writes that really happened in this run.

A model can write "I downgraded b_000002 to 0.4" without ever calling downgrade_belief. The
tool log is the ground truth, so this module compares the answer text with it. Two things are
checked: a claimed downgrade or update needs a successful call of that tool, and every belief id
named in the answer must have been returned by a tool in this run. The reverse also holds: every
belief the run really wrote must be named in the answer. Sentences that deny a write ("I made no
writes", "left unchanged") are not claims and are skipped.

Fixes in v5.1 (Scenario B step-limit failures; two separate causes): an id counts as "returned" only if it appears in
a successful tool result (an id echoed in an error message or typed by the model does not), and
describing what memory already holds ("the belief is recorded in memory") is no longer read as a
claim that this run wrote something. A belief the answer calls "active" must still be active
according to this run's results (the lowered copy is superseded once the sensor belief is
written). A denial that starts with "No" ("No stored belief was
downgraded") is no longer turned into a claim by the leading-word rule.
"""

from __future__ import annotations

import json
import re
from typing import Any

BELIEF_ID = re.compile(r"\bb_\d{3,}\b")
DOWNGRADE_WORDS = re.compile(r"\bdowngrad(?:e|ed|ing)\b", re.IGNORECASE)
UPDATE_VERBS = re.compile(
    r"\b(?:recorded|updated|added|created|wrote|written|saved)\b", re.IGNORECASE
)
UPDATE_OBJECT = re.compile(r"\b(?:belief|beliefs|memory|graph)\b", re.IGNORECASE)
# "memory has been updated": a passive claim with no first-person subject.
PASSIVE_UPDATE = re.compile(
    r"\b(?:memory|graph)\b[^.!?\n]*?\b(?:has|have)\s+been\s+(?:updated|recorded|changed)\b",
    re.IGNORECASE,
)
FIRST_PERSON = re.compile(r"\b(?:i|we)\b", re.IGNORECASE)
WORDS = re.compile(r"[A-Za-z_']+")
# "... is recorded as disputed" / "was recorded in memory" describe what memory holds; they do
# not say that this run wrote anything.
STATIVE_BEFORE = frozenset({"is", "are", "was", "were"})
# Words allowed between the verb and its object for "recorded a new belief" to count as a claim.
FILLER = frozenset(
    {"a", "an", "the", "my", "our", "your", "new", "stored", "this", "that", "belief"}
)
# "No stored belief was downgraded" and "No new belief was recorded" deny a write: "no" followed,
# within two words, by what was not written.
NEGATION = re.compile(
    r"\b(?:not|never|nothing|none|without|unchanged|neither|nor)\b"
    r"|\bno\s+(?:\w+\s+){0,2}(?:belief|beliefs|writes?|updates?|changes?|downgrades?|memory|graph)\b"
    r"|n't",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
# Only an answer word set off by punctuation ("No, my route..." / "Yes: ...") is dropped. A bare
# "No stored belief was downgraded" keeps its "No": that word is what makes it a denial.
LEADING_ANSWER_WORD = re.compile(r"^\W*(?:yes|no)\b[,.:]\s*", re.IGNORECASE)


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


def returned_belief_ids(tool_log: list[dict[str, Any]]) -> set[str]:
    """Every belief id that a successful tool result in this run contained.

    Ids in tool arguments (typed by the model) and in error messages (the guard echoes a
    refused id back) do not count: they would let an invented id through.
    """
    seen: set[str] = set()
    for entry in tool_log:
        result = entry["result"]
        if result["ok"]:
            seen.update(BELIEF_ID.findall(json.dumps(result["data"])))
    return seen


def effective_statuses(tool_log: list[dict[str, Any]]) -> dict[str, str]:
    """Belief id -> its status as the tool results of this run imply it now stands.

    A belief is copied into a result when it is written, so that copy goes stale: the lowered
    copy b_000004 reads "active" in the downgrade result and is superseded the moment the update
    returns b_000005 with `supersedes: b_000004`. The latest copy of each id is therefore
    overridden to "superseded" when a later result names it in `supersedes`.
    """
    status: dict[str, str] = {}
    replaced: set[str] = set()
    for entry in tool_log:
        result = entry["result"]
        if not result["ok"]:
            continue
        data = result["data"]
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and isinstance(item.get("belief_id"), str):
                if isinstance(item.get("status"), str):
                    status[item["belief_id"]] = item["status"]
                if isinstance(item.get("supersedes"), str):
                    replaced.add(item["supersedes"])
    for belief_id in replaced:
        status[belief_id] = "superseded"
    return status


ACTIVE_WORD = re.compile(r"\bactive\b", re.IGNORECASE)
# A sentence that says one belief replaced another explains the chain itself.
SENTENCE_EXPLAINS_CHAIN = re.compile(r"supersed|replac", re.IGNORECASE)
# A segment that already explains the status ("superseded", "no longer active") is not a claim.
STATUS_EXPLAINED = re.compile(r"supersed|no longer|inactive|\bnot\b", re.IGNORECASE)


def wrong_active_claims(answer: str, statuses: dict[str, str]) -> list[str]:
    """Belief ids the answer calls active although this run's results show they are not.

    The text after an id, up to the next id or the end of the sentence, is what describes it:
    in "recorded b_000005 as active" the word belongs to b_000005, not to the id before it.
    Sentences that say one belief superseded or replaced another are skipped.
    """
    wrong: list[str] = []
    for sentence in (x.strip() for x in SENTENCE_SPLIT.split(answer) if x.strip()):
        if SENTENCE_EXPLAINS_CHAIN.search(sentence):
            continue
        ids = list(BELIEF_ID.finditer(sentence))
        for position, found in enumerate(ids):
            belief_id = found.group()
            if statuses.get(belief_id, "active") == "active" or belief_id in wrong:
                continue
            end = (
                ids[position + 1].start() if position + 1 < len(ids) else len(sentence)
            )
            described = sentence[found.end() : end]
            if ACTIVE_WORD.search(described) and not STATUS_EXPLAINED.search(described):
                wrong.append(belief_id)
    return wrong


def _is_downgrade_claim(sentence: str) -> bool:
    body = LEADING_ANSWER_WORD.sub("", sentence, count=1)
    return bool(DOWNGRADE_WORDS.search(body)) and not NEGATION.search(body)


def _is_update_claim(sentence: str) -> bool:
    """True if the sentence says that this run recorded, added or updated something."""
    body = LEADING_ANSWER_WORD.sub("", sentence, count=1)
    if NEGATION.search(body):
        return False
    if PASSIVE_UPDATE.search(body):
        return True
    for verb in UPDATE_VERBS.finditer(body):
        before = body[: verb.start()]
        previous = WORDS.findall(before)
        if previous and previous[-1].lower() in STATIVE_BEFORE:
            continue  # "is recorded as ...": a description of memory, not a write claim
        target = UPDATE_OBJECT.search(body, verb.end())
        if target is None:
            continue
        gap = WORDS.findall(body[verb.end() : target.start()])
        if all(word.lower() in FILLER for word in gap) or FIRST_PERSON.search(before):
            return True
    return False


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
        _is_downgrade_claim(s) for s in sentences
    ):
        problems.append("you claim a downgrade, but no downgrade_belief call succeeded")
    if not _succeeded(tool_log, "update_belief") and any(
        _is_update_claim(s) for s in sentences
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
    unknown = sorted(named - returned_belief_ids(tool_log))
    if unknown:
        problems.append("you name belief ids no tool returned: " + ", ".join(unknown))
    statuses = effective_statuses(tool_log)
    for belief_id in wrong_active_claims(answer, statuses):
        problems.append(
            f"you call {belief_id} active, but this run's results show it is "
            f"{statuses[belief_id]}: report its status as {statuses[belief_id]}"
        )
    return problems
