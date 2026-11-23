"""The reliability result must be attributable to distinct, internally linked runs."""

import json

import pytest

from evaluation.role4.integration.offline import offline_guard
from evaluation.runner import run_case
from evaluation.summarize import results_table, summarize


def test_scope_and_deduplication_of_recorded_trials(tmp_path):
    with offline_guard() as blocked:
        run_case("T01", tmp_path, run_id="first")
    assert blocked == []
    results = summarize([tmp_path])
    assert results["totals"]["scripted_llm"]["passes"] == 1
    assert results["totals"]["live"]["runs"] == 0
    assert "| T01 | 1/1 | Not run |" in results_table(results)
    with pytest.raises(ValueError, match="Duplicate run ID"):
        summarize([tmp_path, tmp_path])


def test_tampered_trace_cannot_contribute_to_results(tmp_path):
    with offline_guard():
        run_case("T10", tmp_path, run_id="first")
    trace = next(tmp_path.rglob("agent_run_*.json"))
    data = json.loads(trace.read_text(encoding="utf-8"))
    data["answer"] = "I moved forward."
    trace.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Trace and test log disagree"):
        summarize([tmp_path])
