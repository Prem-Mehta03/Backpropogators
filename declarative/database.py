"""SQLite persistence for belief provenance and immutable history."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from contracts.models import Belief


class BeliefDatabase:
    """Persist validated beliefs in SQLite while retaining their full history."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        """Open a database and ensure its schema exists."""
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        """Create the provenance table and indexes if absent."""
        self._connection.execute("""CREATE TABLE IF NOT EXISTS beliefs (
                belief_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                perspective TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_beliefs_subject_predicate ON beliefs(subject, predicate, timestamp)"
        )
        self._connection.commit()

    def insert(self, belief: Belief) -> None:
        """Insert a new immutable belief record."""
        payload = belief.model_dump_json()
        self._connection.execute(
            "INSERT INTO beliefs (belief_id, subject, predicate, perspective, status, timestamp, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                belief.belief_id,
                belief.subject,
                belief.predicate,
                belief.perspective,
                belief.status,
                belief.timestamp,
                payload,
            ),
        )
        self._connection.commit()

    def replace(self, belief: Belief) -> None:
        """Update one belief's state while leaving all other history intact."""
        cursor = self._connection.execute(
            "UPDATE beliefs SET status=?, payload=? WHERE belief_id=?",
            (belief.status, belief.model_dump_json(), belief.belief_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(belief.belief_id)
        self._connection.commit()

    def append_with_supersession(self, prior: Belief, successor: Belief) -> None:
        """Atomically close one prior belief and insert its successor."""
        closed = prior.model_copy(
            update={"status": "superseded", "valid_to": successor.timestamp}
        )
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE beliefs SET status=?, payload=? WHERE belief_id=?",
                (closed.status, closed.model_dump_json(), closed.belief_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(prior.belief_id)
            self._connection.execute(
                "INSERT INTO beliefs (belief_id, subject, predicate, perspective, status, timestamp, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    successor.belief_id,
                    successor.subject,
                    successor.predicate,
                    successor.perspective,
                    successor.status,
                    successor.timestamp,
                    successor.model_dump_json(),
                ),
            )

    def get(self, belief_id: str) -> Belief | None:
        """Fetch a belief by ID, returning None when it does not exist."""
        row = self._connection.execute(
            "SELECT payload FROM beliefs WHERE belief_id=?", (belief_id,)
        ).fetchone()
        return Belief.model_validate_json(row["payload"]) if row else None

    def list_beliefs(self, subject: str, predicate: str | None = None) -> list[Belief]:
        """Fetch all beliefs for a subject in chronological order."""
        if predicate is None:
            rows = self._connection.execute(
                "SELECT payload FROM beliefs WHERE subject=? ORDER BY timestamp, belief_id",
                (subject,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT payload FROM beliefs WHERE subject=? AND predicate=? ORDER BY timestamp, belief_id",
                (subject, predicate),
            ).fetchall()
        return [Belief.model_validate_json(row["payload"]) for row in rows]

    def list_active(self, subject: str, predicate: str | None = None) -> list[Belief]:
        """Fetch current active or disputed beliefs for a subject."""
        items = self.list_beliefs(subject, predicate)
        return [item for item in items if item.status in ("active", "disputed")]

    def list_beliefs_for_all(self) -> list[Belief]:
        """Fetch all beliefs in chronological order for graph reconstruction."""
        rows = self._connection.execute(
            "SELECT payload FROM beliefs ORDER BY timestamp, belief_id"
        ).fetchall()
        return [Belief.model_validate_json(row["payload"]) for row in rows]

    def next_id(self) -> str:
        """Return the next sequential contract belief ID."""
        row = self._connection.execute(
            "SELECT MAX(CAST(SUBSTR(belief_id, 3) AS INTEGER)) AS max_id FROM beliefs"
        ).fetchone()
        return f"b_{(row['max_id'] or 0) + 1:06d}"

    def reset(self) -> None:
        """Delete all stored beliefs for a deterministic test reset."""
        self._connection.execute("DELETE FROM beliefs")
        self._connection.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    def export_payloads(self) -> list[dict[str, Any]]:
        """Return every stored belief as a JSON-compatible mapping."""
        rows = self._connection.execute(
            "SELECT payload FROM beliefs ORDER BY timestamp, belief_id"
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
