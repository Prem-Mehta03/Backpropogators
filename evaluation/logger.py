"""JSONL logging for tool calls, memory changes, and automated test runs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.version import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

logger = logging.getLogger(__name__)

_TEST_FIELDS = frozenset({
    "question", "state_before", "tool_calls", "state_after", "answer",
    "expected", "checks", "result",
})
_IDENTITY_FIELDS = frozenset({"schema_version", "test_id", "run_id"})


def _validate_test_payload(payload: dict[str, Any]) -> None:
    missing = _TEST_FIELDS.difference(payload)
    if missing:
        raise ValueError(f"test log missing fields: {', '.join(sorted(missing))}")
    if payload["result"] not in ("PASS", "FAIL"):
        raise ValueError("test log result must be PASS or FAIL")
    if not isinstance(payload["state_before"], dict) or not isinstance(payload["state_after"], dict):
        raise TypeError("test log states must be objects")
    if not isinstance(payload["tool_calls"], list) or not isinstance(payload["checks"], list):
        raise TypeError("tool_calls and checks must be lists")
    for field in ("model", "trace_file"):
        if field in payload and (
            not isinstance(payload[field], str) or not payload[field].strip()
        ):
            raise ValueError(f"{field} must be a nonempty string when supplied")
    if "answer_source" in payload and payload["answer_source"] not in ("llm", "fallback_summary"):
        raise ValueError("answer_source must be llm or fallback_summary")


def load_test_log(path: str | Path) -> dict[str, Any]:
    """Read a v1.0 or v1.1 evaluation record. Raise for malformed or unsupported data."""
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("schema_version"), str)
        or record["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise ValueError("unsupported test log schema version")
    for field in ("test_id", "run_id"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"test log {field} must be nonempty")
    _validate_test_payload(record)
    return record


class EvaluationLogger:
    """Write deterministic, machine-readable project events and test logs."""

    def __init__(self, log_dir: str | Path = "evaluation/logs") -> None:
        """Create a logger targeting the requested log directory."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_event(
        self,
        run_id: str,
        event_type: str,
        details: dict[str, Any],
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one structured event and return the JSON-compatible record."""
        if not run_id.strip() or not event_type.strip():
            raise ValueError("run_id and event_type must be non-empty")
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "event_id": event_id or f"{run_id}:{timestamp}:{event_type}",
            "event_type": event_type,
            "timestamp": timestamp,
            "details": details,
        }
        self._append(self.log_dir / "events.jsonl", record)
        return record

    def write_test_log(
        self, test_id: str, run_id: str, payload: dict[str, Any]
    ) -> Path:
        """Write the standard evaluation record to a test-specific JSON file."""
        _validate_test_payload(payload)
        if not test_id.strip() or not run_id.strip():
            raise ValueError("test_id and run_id must be non-empty")
        if _IDENTITY_FIELDS.intersection(payload):
            raise ValueError("test log payload cannot override its identity or schema version")
        record = {
            "schema_version": SCHEMA_VERSION,
            "test_id": test_id,
            "run_id": run_id,
            **payload,
        }
        safe_id = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in test_id
        )
        safe_run_id = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in run_id
        )
        path = self.log_dir / f"{safe_id}__{safe_run_id}.json"
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return path

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        """Append one JSON record to a JSON Lines file."""
        try:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
                )
        except OSError:
            logger.exception("Unable to append evaluation event")
            raise
