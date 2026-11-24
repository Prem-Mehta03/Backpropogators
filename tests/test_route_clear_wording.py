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
