"""Certainty checks: what an answer must say when the evidence is weak, split or stale.

Three live failures, one rule each (Guidelines 2: rules in code, not only in the prompt).

T04 (live, 0/3 then 0/3 again): the LiDAR read blocked at 12 cm with confidence 0.4. First the
agent answered "Yes, the route is clear". After the first fix it answered correctly in substance
but never said the evidence "conflicts" or suggested a "recheck". So a weak reading or two
disagreeing forward distance sensors now require an answer that (a) does not open with "Yes" or
call the route clear as fact, (b) uses the word conflict or disagree, (c) for a weak reading,
says it is weak, and (d) suggests a recheck or another reading.

T05 (live): two sensors disagreed (LiDAR 250 cm clear through glass, ultrasonic 15 cm blocked)
but the agent recorded nothing, so memory never marked the state disputed. Each disagreeing
sensor's reading must be recorded with update_belief (the guard already makes sure the value,
source and confidence are the sensor's own) before the answer is accepted. Recording is not
downgrading: the stored belief stays.

T06 (live, 0/3): the history showed an older map entry replaced by a newer plan, but the answer
never called it stale. An answer must say stale or outdated, and name the entry by date or source,
for every belief that was already superseded when the run began (history read before the run's
first write; the run's own supersessions are not stale).

Like the claim check, a refusal is bounded by MAX_CLAIM_REFUSALS; after that the deterministic
summary is used, which states the same things.
"""

from __future__ import annotations

import re
from typing import Any

from contracts.policy import LIVE_SENSOR_MIN
from procedural.answer_text import normalize_answer_text
from procedural.update_guard import distance_readings

# Models write hyphens as look-alikes ("re‑read", U+2011). Words are matched on plain hyphens.
_HYPHEN_LOOKALIKES = re.compile("[‐‑‒–—−]")


def _plain(text: str) -> str:
    return normalize_answer_text(_HYPHEN_LOOKALIKES.sub("-", text))


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
OPENS_WITH_YES = re.compile(r"^\W*yes\b", re.IGNORECASE)
_ROUTE_SUBJECT = r"(?:route|path(?:_[a-z0-9]+)?|way|corridor)"
# A positive claim about the route itself, rather than a bare sensor status.
CLEAR_AS_FACT = re.compile(
    rf"\b{_ROUTE_SUBJECT}\b[^.!?]{{0,40}}?\b(?:is|remains)\s+"
    r"(?:(?:now|currently|definitely|indeed|considered|completely|entirely)\s+)*clear\b",
    re.IGNORECASE,
)
# A contrast or a new coordinated statement ends the previous qualification. Ordinary
# commas are kept, for example in "According to the map, the route is clear."
_CLAUSE_SPLIT = re.compile(
    r"\s*;\s*|[,\s-]+\b(?:but|however|nevertheless|nonetheless|whereas)\b[\s,]+"
    rf"|,\s*(?:and|so|yet)\s+(?=(?:(?:the|this|our|my)\s+)?{_ROUTE_SUBJECT}\b)"
    r"|\s+(?:and|so|yet)\s+(?=(?:I|we)\b)"
    rf"|\s+(?:so|yet)\s+(?=(?:(?:the|this|our|my)\s+)?{_ROUTE_SUBJECT}\b)",
    re.IGNORECASE,
)
_CONCESSIVE_START = re.compile(r"^\W*(?:although|even though|while)\b", re.IGNORECASE)
_CLAIM_QUALIFIER = re.compile(
    r"\b(?:whether|if|assuming|according\s+to|as\s+(?:reported|shown|indicated)\s+by)\b"
    r"|\b(?:cannot|can['’]t|could\s+not|couldn['’]t|do\s+not|don['’]t|did\s+not|didn['’]t"
    r"|unable\s+to)\s+(?:yet\s+)?(?:confirm|tell|verify|determine|say|know|think|conclude)\b"
    r"|\b(?:not\s+(?:able|sure)|unclear|no\s+(?:usable\s+)?evidence\s+that)\b"
    r"|\b(?:map|default_map|floor[_ ]plan(?:_rev[0-9]+)?|belief|reading|record|memory|user|sensor"
    r"|lidar(?:_front)?|ultrasonic(?:_front)?)"
    r"\b(?:\s*:|[^,;]{0,45}\b(?:says?|said|states?|stated|indicates?|indicated|reports?|reported|shows?|showed"
    r"|suggests?|suggested|labels?|labeled)\b)",
    re.IGNORECASE,
)
_TRAILING_QUALIFIER = re.compile(
    r"^[\s,(]*(?:according\s+to|as\s+(?:reported|shown|indicated)\s+by|per|if|only\s+if|assuming)\b",
    re.IGNORECASE,
)


def asserts_route_clear(answer: str) -> bool:
    """Check for a direct clearance claim, ignoring its own hedge or source attribution.

    A qualification in one clause does not excuse an independent clearance claim in
    another clause or sentence. An opening "Yes" still counts for a route question.
    """
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(_plain(answer)) if s.strip()]
    if sentences and OPENS_WITH_YES.search(sentences[0]):
        return True
    for sentence in sentences:
        clauses = _CLAUSE_SPLIT.split(sentence)
        for clause in clauses:
            parts = clause.split(",", 1) if _CONCESSIVE_START.search(clause) else [clause]
            for part in parts:
                for claim in CLEAR_AS_FACT.finditer(part):
                    # Include local qualifiers inside the match, such as a parenthetical
                    # attribution between "route" and "is clear".
                    qualified = _CLAIM_QUALIFIER.search(part[: claim.end()])
                    attributed_afterward = _TRAILING_QUALIFIER.search(part[claim.end() :])
                    if not (qualified or attributed_afterward):
                        return True
    return False


# The words the T04 and T05 specs use: say the evidence conflicts / is weak, suggest a recheck.
# "recheck" and "another reading" satisfy both specs, so they are the accepted wording.
CONFLICT_WORDS = re.compile(r"conflict|disagree|contradict", re.IGNORECASE)
WEAK_WORDS = re.compile(
    r"\bweak\b|low confidence|too low|unreliable|not (?:strong|reliable) enough",
    re.IGNORECASE,
)
RECHECK_WORDS = re.compile(r"re-?check|another reading", re.IGNORECASE)
# Two disagreeing sensors: the T05 spec also accepts "more evidence".
MORE_EVIDENCE_WORDS = re.compile(
    r"re-?check|another reading|more evidence", re.IGNORECASE
)
STALE_WORDS = re.compile(r"stale|outdated|out of date|out-of-date", re.IGNORECASE)


def weak_or_disputed_kind(tool_log: list[dict[str, Any]]) -> tuple[str, str] | None:
    """('weak' or 'disagree', reason) for this run's route evidence, or None when it is solid."""
    readings = distance_readings(tool_log)
    for name, reading in sorted(readings.items()):
        if reading["confidence"] < LIVE_SENSOR_MIN:
            return (
                "weak",
                (
                    f"the {name} reading has confidence {reading['confidence']}, below the "
                    f"{LIVE_SENSOR_MIN} needed to overrule a stored belief"
                ),
            )
    if len(readings) >= 2 and len({r["status"] for r in readings.values()}) > 1:
        shown = ", ".join(f"{n} {r['status']}" for n, r in sorted(readings.items()))
        return "disagree", f"the forward distance sensors disagree ({shown})"
    return None


def weak_or_disputed_reason(tool_log: list[dict[str, Any]]) -> str | None:
    """Why this run's evidence about the route is weak or disputed, or None when it is not."""
    found = weak_or_disputed_kind(tool_log)
    return None if found is None else found[1]


def overclaimed_certainty(answer: str, tool_log: list[dict[str, Any]]) -> list[str]:
    """Problems with an answer that states or implies certainty the evidence cannot support.

    Inputs: the answer text and the run's tool log. Output: one description per problem;
    [] when the evidence is solid or the answer is appropriately cautious.
    """
    found = weak_or_disputed_kind(tool_log)
    if found is None:
        return []
    kind, reason = found
    answer = _plain(answer)
    problems: list[str] = []
    if asserts_route_clear(answer):
        problems.append(
            f"you state that the route is clear as fact, but {reason}: do not answer "
            "yes or clear; say that you cannot confirm the route"
        )
    if not CONFLICT_WORDS.search(answer):
        problems.append(
            f"you do not say that the evidence conflicts (use the word 'conflict' or "
            f"'disagree'), although {reason}"
        )
    if kind == "weak" and not WEAK_WORDS.search(answer):
        problems.append(
            f"you do not say that the reading is weak or low confidence, although {reason}"
        )
    asked = (MORE_EVIDENCE_WORDS if kind == "disagree" else RECHECK_WORDS).search(
        answer
    )
    if not asked:
        problems.append(
            "you do not suggest a recheck: say that the sensors should be rechecked or read "
            "for another reading"
            + (", or ask for more evidence" if kind == "disagree" else "")
        )
    return problems


def unrecorded_disagreement(tool_log: list[dict[str, Any]]) -> list[str]:
    """Problems when disagreeing distance sensors were read but not recorded in memory.

    Memory can only mark the state disputed once both readings are recorded as agent_sensor
    beliefs. Recording is not downgrading: the stored belief stays as it is. Only readings the
    model asked for count: a disagreement that only the automatic recheck before a move found
    (the move is cancelled) needs the conflict wording, not a memory write.
    """
    reads = [e for e in tool_log if e["tool"] in ("read_lidar", "read_ultrasonic")]
    found = weak_or_disputed_kind(reads)
    if found is None or found[0] != "disagree":
        return []
    recorded = {
        entry["args"].get("source")
        for entry in tool_log
        if entry["tool"] == "update_belief" and entry["result"]["ok"]
    }
    missing = sorted(set(distance_readings(reads)) - recorded)
    if not missing:
        return []
    return [
        (
            f"{found[1]}, but you have not recorded the reading of {', '.join(missing)} in "
            "memory: call update_belief for each (subject path_A, predicate status, object the "
            "reading's status, source the sensor name, perspective agent_sensor) so memory "
            "marks the state disputed. Do not downgrade the stored belief"
        )
    ]


def already_stale(tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Path beliefs that were already superseded when this run began.

    Taken from history lookups made before the run's first successful write, so the run's own
    downgrade and update (which supersede the old map belief) never count as stale.
    """
    stale: list[dict[str, Any]] = []
    for entry in tool_log:
        ok = entry["result"]["ok"]
        if entry["tool"] in ("update_belief", "downgrade_belief") and ok:
            break
        data = entry["result"].get("data") if ok else None
        if entry["tool"] == "get_belief_history" and isinstance(data, list):
            stale += [
                b
                for b in data
                if isinstance(b, dict)
                and b.get("status") == "superseded"
                and b.get("valid_to")
                and str(b.get("subject", "")).startswith("path_")
            ]
    return stale


def undisclosed_stale_belief(answer: str, tool_log: list[dict[str, Any]]) -> list[str]:
    """Problems when an already-superseded belief is not called stale or outdated."""
    problems = []
    for belief in already_stale(tool_log):
        date = str(belief.get("timestamp", ""))[:10]
        named = (belief.get("source") and str(belief["source"]) in answer) or (
            date and date in answer
        )
        if not (STALE_WORDS.search(answer) and named):
            problems.append(
                f"the history shows {belief['belief_id']} ({belief.get('source')}, "
                f"{date}) was already superseded: say it is stale or outdated, with its date "
                "and source, and rely on the newer belief"
            )
    return problems


def certainty_problems(answer: str, tool_log: list[dict[str, Any]]) -> list[str]:
    """All certainty problems with an answer, in a fixed order."""
    return [
        *overclaimed_certainty(answer, tool_log),
        *unrecorded_disagreement(tool_log),
        *undisclosed_stale_belief(_plain(answer), tool_log),
    ]
