"""Write one structured event per line, with stable keys and no global state."""

import json
from pathlib import Path
from evaluation.role4.models import Event, EvaluationResult, TestRunRecord, event_from_dict, utc_now


def write_json(path: str | Path, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def read_events(path: str | Path) -> list[Event]:
    events = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                events.append(event_from_dict(json.loads(line)))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid event at line {line_number}: {exc}") from exc
    return events


class EventLogger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Each named demo run replaces its own previous log; never append stale runs.
        self.stream = self.path.open("w", encoding="utf-8", newline="\n")

    def __enter__(self) -> "EventLogger":
        return self

    def __exit__(self, *args) -> None:
        self.stream.close()

    def record(self, event: Event) -> None:
        self.stream.write(json.dumps(event.to_dict(), sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()

    def record_run(self, run: TestRunRecord, result: EvaluationResult) -> None:
        for event in run.events:
            self.record(event)
        self.record(Event(utc_now(), "beliefs_after", run.scenario_id,
                          {"beliefs": [b.to_dict() for b in run.final_beliefs]}))
        for check in result.checks:
            self.record(Event(utc_now(), "evaluation_check", run.scenario_id, check))
        self.record(Event(utc_now(), "evaluation_result", run.scenario_id, result.to_dict()))
