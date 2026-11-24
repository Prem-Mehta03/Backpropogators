"""Certainty check: an answer may not state the route is clear on weak or disputed evidence.

Test T04 (live, 0/3): the LiDAR read blocked at 12 cm with confidence 0.4 and the agent still
answered "Yes, the route is clear", or "The route is considered clear". The state checks passed
(nothing was downgraded) but the answer was wrong in substance. The rule belongs in code, like
the claim check, not only in the prompt (Guidelines 2).

Evidence is weak or disputed when, in this run, a forward distance sensor read below
LIVE_SENSOR_MIN, or two forward distance sensors disagree. (A disputed belief is not a trigger:
it follows from those two causes, and a memory-layer timestamp tie can also produce one.)
In that case an answer must (a) not open with "Yes" or call the route clear as fact,
and (b) say that the evidence conflicts or is weak, and suggest more evidence or a recheck.
Like the claim check, a refusal is bounded by MAX_CLAIM_REFUSALS; after that the deterministic
summary is used, which states the same things.
"""

from __future__ import annotations

import re
from typing import Any

from contracts.policy import LIVE_SENSOR_MIN
from procedural.update_guard import distance_readings

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
OPENS_WITH_YES = re.compile(r"^\W*yes\b", re.IGNORECASE)
# "the route is (now|considered) clear" stated by the agent itself, not attributed to a source
CLEAR_AS_FACT = re.compile(
    r"\b(?:route|path|way|corridor)\b[^.!?]{0,40}\bis\s+(?:now\s+|currently\s+)?"
    r"(?:considered\s+)?clear\b",
    re.IGNORECASE,
)
ATTRIBUTED_OR_HEDGED = re.compile(
    r"\b(?:says?|said|states?|stored|belief|map|reading|indicates?|reports?|according|"
    r"if|whether|not|unclear|cannot|can't)\b|n't",
    re.IGNORECASE,
)
CONFLICT_WORDS = re.compile(
    r"conflict|disagree|disput|contradict|\bweak\b|too low|low confidence|unreliable|"
    r"uncertain|cannot confirm|can't confirm|unable to confirm|not enough|insufficient",
    re.IGNORECASE,
)
MORE_EVIDENCE_WORDS = re.compile(
    r"recheck|re-check|read again|re-read|read the sensors?|another (?:reading|observation)|"
    r"(?:stronger|new|better) (?:reading|observation|evidence)|"
    r"(?:more|further|additional) (?:evidence|data|readings?|observations?)|verify",
    re.IGNORECASE,
)


def weak_or_disputed_reason(tool_log: list[dict[str, Any]]) -> str | None:
    """Why this run's evidence about the route is weak or disputed, or None when it is not."""
    readings = distance_readings(tool_log)
    for name, reading in sorted(readings.items()):
        if reading["confidence"] < LIVE_SENSOR_MIN:
            return (
                f"the {name} reading has confidence {reading['confidence']}, below the "
                f"{LIVE_SENSOR_MIN} needed to overrule a stored belief"
            )
    if len(readings) >= 2 and len({r["status"] for r in readings.values()}) > 1:
        shown = ", ".join(f"{n} {r['status']}" for n, r in sorted(readings.items()))
        return f"the forward distance sensors disagree ({shown})"
    return None


def overclaimed_certainty(answer: str, tool_log: list[dict[str, Any]]) -> list[str]:
    """Problems with an answer that states or implies certainty the evidence cannot support.

    Inputs: the answer text and the run's tool log. Output: one description per problem;
    [] when the evidence is solid or the answer is appropriately cautious.
    """
    reason = weak_or_disputed_reason(tool_log)
    if reason is None:
        return []
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(answer) if s.strip()]
    problems: list[str] = []
    first = sentences[0] if sentences else ""
    if OPENS_WITH_YES.search(first) or (
        CLEAR_AS_FACT.search(first) and not ATTRIBUTED_OR_HEDGED.search(first)
    ):
        problems.append(
            f"you state that the route is clear as fact, but {reason}: do not answer "
            "yes or clear; say that the evidence is weak or conflicting and that you cannot "
            "confirm the route"
        )
    if not CONFLICT_WORDS.search(answer):
        problems.append(
            f"you do not say that the evidence conflicts or is weak, although {reason}"
        )
    if not MORE_EVIDENCE_WORDS.search(answer):
        problems.append(
            "you do not suggest reading the sensors again or getting more evidence"
        )
    return problems
