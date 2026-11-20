"""Check the final suite's evidence contract and separation of observed outcomes."""

import json

import pytest

from contracts.validators import success_result
from evaluation.role4.final_suite import run_suite
from evaluation.role4.integration.conformance import validate_tool_output
from evaluation.role4.integration.offline import offline_guard


def test_tool_output_rejects_success_with_wrong_payload_or_tool() -> None:
    stamp = "2026-10-03T09:16:00Z"
    with pytest.raises(ValueError):
        validate_tool_output("query_belief", success_result("query_belief", {}, stamp))
    with pytest.raises(ValueError, match="Expected envelope"):
        validate_tool_output("read_lidar", success_result("query_belief", [], stamp))


def test_final_suite_separates_good_runs_known_failures_and_scoped_probe(tmp_path) -> None:
    output = tmp_path / "final"
    with offline_guard() as blocked:
        summary = run_suite(output, trials=2, seed=11, scenarios=("S07", "S08"), blocked=blocked)

    assert blocked == []
    assert summary["unexpected_outcomes"] == []
    assert summary["counts"]["reference"]["passes"] == 4
    assert summary["counts"]["reference_control"]["fails"] == 2
    assert summary["counts"]["canonical"]["passes"] == 4
    assert summary["counts"]["canonical_control"]["fails"] == 1
    assert len(summary["canonical_behavior_gaps"]) == 3  # two temperature probes, one movement defect
    assert all(row["stable_tool_sequence_and_checks"] for row in summary["metrics"])
    assert summary["conformance"] == {"passed": True, "tools": 11, "samples": 14,
                                       "evidence": "contract_conformance.json"}
    for row in summary["runs"]:
        run = json.loads((output / row["evidence"]).read_text(encoding="utf-8"))
        assert run["schema_version"] == "1.0"
        assert run["run_id"] == row["run_id"]
        assert {"question", "answer", "expected", "tool_calls", "state_before", "state_after", "checks"} <= run.keys()
        assert run["result"] == row["result"]
        assert run["failure_layers"] == row["failure_layers"]
