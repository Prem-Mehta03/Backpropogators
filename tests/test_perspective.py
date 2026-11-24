"""Final scripted runs on canonical layers for perspective and abstention."""

import pytest

from evaluation.role4.integration.offline import offline_guard
from evaluation.runner import run_case


@pytest.mark.parametrize("test_id", ["T03", "T07", "T08", "B_APPROACH"])
def test_canonical_perspective(test_id, tmp_path):
    with offline_guard() as blocked:
        log = run_case(test_id, tmp_path, run_id="offline")
    assert not blocked
    assert log["result"] == "PASS", [c for c in log["checks"] if not c["passed"]]
