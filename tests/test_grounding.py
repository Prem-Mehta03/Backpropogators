"""Final scripted runs on canonical layers for grounding and action safety."""

import pytest

from evaluation.role4.integration.offline import offline_guard
from evaluation.runner import run_case


@pytest.mark.parametrize("test_id", ["T01", "T02", "T04", "T05", "T06", "T09", "T10"])
def test_canonical_grounding(test_id, tmp_path):
    with offline_guard() as blocked:
        log = run_case(test_id, tmp_path, run_id="offline")
    assert not blocked
    assert log["result"] == "PASS", [c for c in log["checks"] if not c["passed"]]
