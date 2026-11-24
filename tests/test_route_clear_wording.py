"""The T04/T05 'does not assert a clear route' check must tell an assertion from a hedge."""

from __future__ import annotations

import pytest

from evaluation.stretch_checks import asserts_route_clear


@pytest.mark.parametrize(
    "answer",
    [
        "Yes, the route is clear.",
        "The route is clear. The LiDAR reading is weak.",
        "The route is definitely clear.",
        "The path is clear.\nNo update was needed.",
    ],
)
def test_real_assertions_are_still_caught(answer: str) -> None:
    assert asserts_route_clear(answer)


@pytest.mark.parametrize(
    "answer",
    [
        # the correct live T04 answer (22:24, round 2) that the old pattern failed
        "I cannot confirm whether the route is clear.\nMy stored belief says the route ahead "
        "(path_A) is clear. The evidence conflicts; please recheck.",
        "My stored belief says the route is clear, but the LiDAR reads 12 cm.",
        "No, the route is not clear.",
        "I cannot confirm the state of the route.",
    ],
)
def test_hedged_or_attributed_sentences_are_not_assertions(answer: str) -> None:
    assert not asserts_route_clear(answer)


# ---- the wording the T04/T05 checks accept (live T05 round 4 failed on a lexical detail only)
import re  # noqa: E402

from evaluation.stretch_checks import ASKS_MORE_EVIDENCE, ASKS_RECHECK, plain_lower  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "I recommend re\u2011checking the sensors or obtaining additional evidence.",  # round 4
        "Please recheck.",
        "We need more evidence.",
        "Further evidence is needed.",
        "Take another reading.",
    ],
)
def test_t05_accepts_the_ways_a_model_asks_for_more_evidence(text: str) -> None:
    assert re.search(ASKS_MORE_EVIDENCE, plain_lower(text))


@pytest.mark.parametrize(
    "text",
    ["Please re\u2011check the sensors.", "recheck", "Check again.", "Take another reading."],
)
def test_t04_accepts_recheck_in_its_usual_spellings(text: str) -> None:
    assert re.search(ASKS_RECHECK, plain_lower(text))


@pytest.mark.parametrize(
    "text",
    ["The sensors disagree.", "I cannot confirm the state of the route.", "Please wait."],
)
def test_text_that_asks_for_nothing_is_still_rejected(text: str) -> None:
    assert not re.search(ASKS_MORE_EVIDENCE, plain_lower(text))
    assert not re.search(ASKS_RECHECK, plain_lower(text))
