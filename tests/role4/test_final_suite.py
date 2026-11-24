"""Check the final suite's evidence contract and separation of observed outcomes."""

import json

import pytest

from contracts.version import SCHEMA_VERSION
from contracts.validators import success_result
from evaluation.role4.final_suite import (
    SCOPED_TEMPERATURE_PROBE,
    SCRIPTED_BEHAVIOR,
    _canonical_behavior_counts,
    run_suite,
)
from evaluation.role4.integration.conformance import validate_tool_output
from evaluation.role4.integration.offline import offline_guard


def test_tool_output_rejects_success_with_wrong_payload_or_tool() -> None:
    stamp = "2026-10-03T09:16:00Z"
    with pytest.raises(ValueError):
        validate_tool_output("query_belief", success_result("query_belief", {}, stamp))
    with pytest.raises(ValueError, match="Expected envelope"):
        validate_tool_output("read_lidar", success_result("query_belief", [], stamp))


def test_final_suite_separates_behavior_passes_and_scoped_probe(tmp_path) -> None:
    output = tmp_path / "final"
    with offline_guard() as blocked:
        summary = run_suite(output, trials=2, seed=11, scenarios=("S07", "S08"), blocked=blocked)

    assert blocked == []
    assert summary["unexpected_outcomes"] == []
    assert summary["counts"]["reference"]["passes"] == 4
    assert summary["counts"]["reference_control"]["fails"] == 2
    assert summary["counts"]["canonical"]["passes"] == 4
    assert summary["counts"]["canonical_control"]["fails"] == 0
    behavior = summary["canonical_behavior"]
    assert behavior == {
        "passes": 2,
        "fails": 0,
        "planned_runs": 4,
        "exercised_runs": 2,
        "pending_runs": 2,
        "pass_rate_over_planned": .5,
        "pass_rate_over_exercised": 1.0,
        "scoped_probes": {"runs": 2, "passes": 2, "evidence": [
            "trial_01/canonical/S07/run.json", "trial_02/canonical/S07/run.json",
        ]},
    }
    assert summary["canonical_behavior_gaps"] == behavior["scoped_probes"]["evidence"]
    assert {row["scenario_id"] for row in summary["metrics"] if row["included_in_canonical_behavior"]} == {"S08"}
    assert all(row["stable_tool_sequence_and_checks"] for row in summary["metrics"])
    assert summary["conformance"] == {"passed": True, "tools": 11, "samples": 14,
                                       "evidence": "contract_conformance.json"}
    for row in summary["runs"]:
        run = json.loads((output / row["evidence"]).read_text(encoding="utf-8"))
        assert run["schema_version"] == SCHEMA_VERSION
        assert run["run_id"] == row["run_id"]
        assert {"question", "answer", "expected", "tool_calls", "state_before", "state_after", "checks"} <= run.keys()
        assert run["result"] == row["result"]
        assert run["failure_layers"] == row["failure_layers"]


def test_count_exercised_failures_but_exclude_scoped_probes_and_controls() -> None:
    records = [
        {"scope": scope, "criteria_scope": criteria, "result": verdict, "evidence": str(i)}
        for i, (scope, criteria, verdict) in enumerate((
            ("canonical", SCRIPTED_BEHAVIOR, "PASS"),
            ("canonical", SCRIPTED_BEHAVIOR, "FAIL"),
            ("canonical", SCOPED_TEMPERATURE_PROBE, "FAIL"),
            ("canonical_control", SCRIPTED_BEHAVIOR, "PASS"),
            ("reference", SCRIPTED_BEHAVIOR, "PASS"),
        ))
    ]
    counts = _canonical_behavior_counts(records)
    assert (counts["passes"], counts["fails"]) == (1, 1)
    assert (counts["planned_runs"], counts["exercised_runs"], counts["pending_runs"]) == (3, 2, 1)
    assert (counts["pass_rate_over_planned"], counts["pass_rate_over_exercised"]) == (1 / 3, .5)
    assert counts["scoped_probes"] == {"runs": 1, "passes": 0, "evidence": ["2"]}
    behavior_only = _canonical_behavior_counts(records[:2])
    assert behavior_only["pending_runs"] == 0
    assert behavior_only["pass_rate_over_planned"] == behavior_only["pass_rate_over_exercised"] == .5
    probes_only = _canonical_behavior_counts(records[2:])
    assert probes_only["pass_rate_over_exercised"] is None
    assert probes_only["pass_rate_over_planned"] == 0
