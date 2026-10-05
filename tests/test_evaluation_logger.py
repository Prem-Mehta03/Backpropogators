"""Tests for Vyom's team evaluation event and test-log writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.logger import EvaluationLogger


def test_event_writer_records_run_id_and_timestamp(tmp_path: Path) -> None:
    """Write a structured JSONL event with the run and event identity."""
    logger = EvaluationLogger(tmp_path)
    event = logger.log_event("run_001", "tool_call", {"tool": "query_belief"})
    saved = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    assert event == saved
    assert saved["run_id"] == "run_001"
    assert saved["schema_version"] == "1.0"
    assert saved["timestamp"].endswith("Z")


def test_test_log_writer_matches_team_fields(tmp_path: Path) -> None:
    """Write a complete test record using the agreed required field names."""
    logger = EvaluationLogger(tmp_path)
    payload = {
        "question": "Is path_A clear?",
        "state_before": {"beliefs": []},
        "tool_calls": [],
        "state_after": {"beliefs": []},
        "answer": "Evidence is missing.",
        "expected": "Abstain when evidence is missing.",
        "checks": [],
        "result": "PASS",
    }
    path = logger.write_test_log("T07_missing_data", "run_001", payload)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "1.0"
    assert saved["test_id"] == "T07_missing_data"
    assert saved["run_id"] == "run_001"
    assert saved["result"] == "PASS"
    second_path = logger.write_test_log("T07_missing_data", "run_002", payload)
    assert second_path != path
    assert path.exists() and second_path.exists()


def test_test_log_rejects_missing_fields(tmp_path: Path) -> None:
    """Reject records that cannot be evaluated from the required evidence."""
    logger = EvaluationLogger(tmp_path)
    with pytest.raises(ValueError, match="missing fields"):
        logger.write_test_log("T01", "run_001", {"question": "missing data"})
