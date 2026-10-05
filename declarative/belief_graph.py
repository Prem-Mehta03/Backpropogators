"""Memory API and in-memory NetworkX view over persistent belief history."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from typing import Any

import networkx as nx
from pydantic import ValidationError

from contracts.models import Belief, BeliefValue
from contracts.validators import error_result, success_result, utc_timestamp
from contracts.version import SCHEMA_VERSION

from .conflicts import find_conflicts, resolve_priority
from .database import BeliefDatabase

logger = logging.getLogger(__name__)


class BeliefMemory:
    """Own the declarative memory API, SQLite provenance store, and belief graph."""

    def __init__(
        self,
        database: BeliefDatabase | None = None,
        clock: Callable[[], str] | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Create memory from a store and rebuild the graph from persisted history.

        Inputs: optional SQLite database, UTC clock function, and callback receiving
        event type/details mappings. Output: a ready BeliefMemory instance. Database
        construction failures are raised locally and must be handled by the factory.
        """
        self.database = database if database is not None else BeliefDatabase()
        self._clock = clock if clock is not None else utc_timestamp
        self._event_callback = event_callback
        self.graph = nx.DiGraph()
        for item in self.database.list_beliefs_for_all():
            self._add_graph_node(item)

    def _add_graph_node(self, belief: Belief) -> None:
        """Add a belief and its supersession edge to the graph view."""
        self.graph.add_node(belief.belief_id, **belief.model_dump(mode="json"))
        if belief.supersedes:
            self.graph.add_edge(
                belief.supersedes, belief.belief_id, relation="supersedes"
            )

    @staticmethod
    def _storage_error(tool: str, exc: Exception) -> dict[str, Any]:
        """Log an internal persistence failure and convert it to the boundary envelope."""
        logger.exception("Declarative storage operation failed: %s", tool)
        return error_result(tool, "STORAGE_ERROR", str(exc), retryable=True)

    def _emit_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Forward a committed state change to the injected event logger callback."""
        if self._event_callback is None:
            return
        try:
            self._event_callback(event_type, details)
        except Exception:
            logger.exception("Unable to record declarative event %s", event_type)

    def _allocate_belief(self, **values: Any) -> Belief:
        """Build a validated belief using this store's ID sequence."""
        confidence = values.get("confidence")
        if (
            values.get("source") is None
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
        ):
            values["confidence"] = min(confidence, 0.5)
        timestamp = (
            values.get("timestamp")
            if values.get("timestamp") is not None
            else self._clock()
        )
        return Belief(
            schema_version=SCHEMA_VERSION,
            belief_id=self.database.next_id(),
            subject=values["subject"],
            predicate=values["predicate"],
            object=values["object"],
            source=values.get("source"),
            confidence=values["confidence"],
            timestamp=timestamp,
            perspective=values["perspective"],
            status=values.get("status", "active"),
            valid_from=(
                values.get("valid_from")
                if values.get("valid_from") is not None
                else timestamp
            ),
            valid_to=values.get("valid_to"),
            supersedes=values.get("supersedes"),
        )

    def add_belief(
        self,
        subject: str,
        predicate: str,
        object: BeliefValue,
        source: str | None,
        confidence: float,
        perspective: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Insert a validated claim and return its ToolResult envelope.

        Inputs: subject, predicate, JSON scalar object, source, confidence, perspective,
        and an optional contract timestamp. Output: the created Belief in a success
        envelope. Error codes: INVALID_ARGUMENT or STORAGE_ERROR.
        """
        try:
            belief = self._allocate_belief(
                subject=subject,
                predicate=predicate,
                object=object,
                source=source,
                confidence=confidence,
                perspective=perspective,
                timestamp=timestamp,
            )
            self.database.insert(belief)
            self._add_graph_node(belief)
            self._emit_event(
                "belief_created", {"after": belief.model_dump(mode="json")}
            )
            return success_result(
                "add_belief", belief.model_dump(mode="json"), belief.timestamp
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return error_result("add_belief", "INVALID_ARGUMENT", str(exc))
        except Exception as exc:
            logger.exception("Failed to add belief")
            return error_result("add_belief", "STORAGE_ERROR", str(exc), retryable=True)

    def query_belief(
        self, subject: str, predicate: str | None = None, perspective: str | None = None
    ) -> dict[str, Any]:
        """Query current beliefs, or all records when filtering one perspective.

        Inputs: required subject and optional predicate/perspective. Output: a list of
        current active/disputed Belief objects when perspective is omitted; a
        perspective-specific query also includes superseded history. Error codes:
        INVALID_ARGUMENT or STORAGE_ERROR.
        """
        if not isinstance(subject, str) or not subject.strip():
            return error_result(
                "query_belief", "INVALID_ARGUMENT", "subject must be non-empty"
            )
        if predicate is not None and (
            not isinstance(predicate, str) or not predicate.strip()
        ):
            return error_result(
                "query_belief",
                "INVALID_ARGUMENT",
                "predicate must be a non-empty string or null",
            )
        if perspective is not None and perspective not in (
            "user",
            "agent_sensor",
            "historical",
            "third_party",
        ):
            return error_result(
                "query_belief", "INVALID_ARGUMENT", "unknown perspective"
            )
        try:
            if perspective is None:
                items = self.database.list_active(subject, predicate)
            else:
                items = self.database.list_beliefs(subject, predicate)
                items = [item for item in items if item.perspective == perspective]
            return success_result(
                "query_belief", [item.model_dump(mode="json") for item in items]
            )
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("query_belief", exc)

    def get_belief(self, belief_id: str) -> dict[str, Any]:
        """Fetch one belief by its declarative ID.

        Input: `b_######` belief ID. Output: the Belief in a success envelope. Error
        codes: INVALID_ARGUMENT, NOT_FOUND, or STORAGE_ERROR.
        """
        if (
            not isinstance(belief_id, str)
            or re.fullmatch(r"b_\d{6}", belief_id) is None
        ):
            return error_result(
                "get_belief",
                "INVALID_ARGUMENT",
                "belief_id must use the b_###### format",
            )
        try:
            item = self.database.get(belief_id)
            if item is None:
                return error_result(
                    "get_belief", "NOT_FOUND", f"No belief with id {belief_id}"
                )
            return success_result(
                "get_belief", item.model_dump(mode="json"), item.timestamp
            )
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("get_belief", exc)

    def get_belief_history(
        self, subject: str, predicate: str | None = None
    ) -> dict[str, Any]:
        """Return a subject's full belief history in chronological order.

        Inputs: subject and optional predicate. Output: a list of Belief objects,
        oldest first, in a success envelope. Error codes: INVALID_ARGUMENT or
        STORAGE_ERROR.
        """
        if not isinstance(subject, str) or not subject.strip():
            return error_result(
                "get_belief_history", "INVALID_ARGUMENT", "subject must be non-empty"
            )
        if predicate is not None and (
            not isinstance(predicate, str) or not predicate.strip()
        ):
            return error_result(
                "get_belief_history",
                "INVALID_ARGUMENT",
                "predicate must be a non-empty string or null",
            )
        try:
            items = self.database.list_beliefs(subject, predicate)
            return success_result(
                "get_belief_history", [item.model_dump(mode="json") for item in items]
            )
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("get_belief_history", exc)

    def get_source(self, belief_id: str) -> dict[str, Any]:
        """Return the source attached to a belief.

        Input: `b_######` belief ID. Output: belief ID and source in a success
        envelope. Error codes: INVALID_ARGUMENT, NOT_FOUND, or STORAGE_ERROR.
        """
        if (
            not isinstance(belief_id, str)
            or re.fullmatch(r"b_\d{6}", belief_id) is None
        ):
            return error_result(
                "get_source",
                "INVALID_ARGUMENT",
                "belief_id must use the b_###### format",
            )
        try:
            item = self.database.get(belief_id)
            if item is None:
                return error_result(
                    "get_source", "NOT_FOUND", f"No belief with id {belief_id}"
                )
            return success_result(
                "get_source",
                {"belief_id": item.belief_id, "source": item.source},
                item.timestamp,
            )
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("get_source", exc)

    def update_belief(
        self,
        subject: str,
        predicate: str,
        object: BeliefValue,
        source: str | None,
        confidence: float,
        perspective: str,
        reason: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Apply evidence priority and append an updated or disputed belief.

        Inputs: subject, predicate, scalar object, source, confidence, perspective,
        reason, and optional evidence timestamp. Output: the new Belief in a success
        envelope. Error codes: INVALID_ARGUMENT or STORAGE_ERROR. Low-confidence or
        unresolved evidence is returned as a disputed Belief, not an error.
        """
        if not isinstance(reason, str) or not reason.strip():
            return error_result(
                "update_belief", "INVALID_ARGUMENT", "reason must be non-empty"
            )
        if not isinstance(subject, str) or not subject.strip():
            return error_result(
                "update_belief", "INVALID_ARGUMENT", "subject must be non-empty"
            )
        if not isinstance(predicate, str) or not predicate.strip():
            return error_result(
                "update_belief", "INVALID_ARGUMENT", "predicate must be non-empty"
            )
        now = timestamp if timestamp is not None else self._clock()
        try:
            proposed = self._allocate_belief(
                subject=subject,
                predicate=predicate,
                object=object,
                source=source,
                confidence=confidence,
                perspective=perspective,
                timestamp=now,
            )
            active = self.database.list_active(subject, predicate)
            same_perspective = next(
                (
                    item
                    for item in reversed(active)
                    if item.perspective == proposed.perspective
                ),
                None,
            )
            historical_conflict = next(
                (
                    item
                    for item in reversed(active)
                    if proposed.perspective == "agent_sensor"
                    and item.perspective == "historical"
                    and item.object != proposed.object
                ),
                None,
            )
            any_conflict = next(
                (item for item in reversed(active) if item.object != proposed.object),
                None,
            )
            prior = same_perspective or historical_conflict
            if prior is None and proposed.perspective != "user":
                prior = any_conflict
            competing_live_sensor = any(
                item.perspective == "agent_sensor"
                and item.source != proposed.source
                and item.object != proposed.object
                for item in active
            )
            decision = resolve_priority(
                prior,
                proposed,
                another_live_sensor_disagrees=(
                    proposed.perspective == "agent_sensor" and competing_live_sensor
                ),
            )
            if decision.action == "dispute":
                belief = proposed.model_copy(
                    update={"status": "disputed", "confidence": decision.confidence}
                )
                self.database.insert(belief)
            elif decision.action == "replace" and prior is not None:
                belief = proposed.model_copy(update={"supersedes": prior.belief_id})
                self.database.append_with_supersession(prior, belief)
                closed = prior.model_copy(
                    update={"status": "superseded", "valid_to": now}
                )
                self._add_graph_node(closed)
            else:
                belief = proposed
                self.database.insert(belief)
            self._add_graph_node(belief)
            self._emit_event(
                "belief_update",
                {
                    "operation": decision.action,
                    "before": (
                        prior.model_dump(mode="json") if prior is not None else None
                    ),
                    "after": belief.model_dump(mode="json"),
                    "reason": reason,
                },
            )
            logger.info(
                "Belief update decision=%s subject=%s predicate=%s reason=%s",
                decision.action,
                subject,
                predicate,
                reason,
            )
            return success_result(
                "update_belief", belief.model_dump(mode="json"), belief.timestamp
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return error_result("update_belief", "INVALID_ARGUMENT", str(exc))
        except Exception as exc:
            logger.exception("Failed to update belief")
            return error_result(
                "update_belief", "STORAGE_ERROR", str(exc), retryable=True
            )

    def downgrade_belief(
        self, belief_id: str, new_confidence: float, reason: str
    ) -> dict[str, Any]:
        """Append a lower-confidence successor while preserving the old record.

        Inputs: belief ID, non-increasing confidence, and reason. Output: the new
        Belief in a success envelope. Error codes: INVALID_ARGUMENT, NOT_FOUND, or
        STORAGE_ERROR.
        """
        if (
            not isinstance(belief_id, str)
            or re.fullmatch(r"b_\d{6}", belief_id) is None
        ):
            return error_result(
                "downgrade_belief",
                "INVALID_ARGUMENT",
                "belief_id must use the b_###### format",
            )
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or isinstance(new_confidence, bool)
            or not isinstance(new_confidence, (int, float))
            or not math.isfinite(new_confidence)
            or new_confidence < 0.0
        ):
            return error_result(
                "downgrade_belief",
                "INVALID_ARGUMENT",
                "reason and a non-increasing confidence are required",
            )
        try:
            prior = self.database.get(belief_id)
            if prior is None:
                return error_result(
                    "downgrade_belief", "NOT_FOUND", f"No belief with id {belief_id}"
                )
            if new_confidence > prior.confidence:
                return error_result(
                    "downgrade_belief",
                    "INVALID_ARGUMENT",
                    "new_confidence must not exceed current confidence",
                )
            now = self._clock()
            successor = self._allocate_belief(
                subject=prior.subject,
                predicate=prior.predicate,
                object=prior.object,
                source=prior.source,
                confidence=new_confidence,
                perspective=prior.perspective,
                timestamp=now,
                supersedes=prior.belief_id,
            )
            self.database.append_with_supersession(prior, successor)
            closed = prior.model_copy(update={"status": "superseded", "valid_to": now})
            self._add_graph_node(closed)
            self._add_graph_node(successor)
            self._emit_event(
                "belief_downgrade",
                {
                    "before": prior.model_dump(mode="json"),
                    "after": successor.model_dump(mode="json"),
                    "reason": reason,
                },
            )
            return success_result(
                "downgrade_belief", successor.model_dump(mode="json"), now
            )
        except (ValidationError, TypeError, ValueError) as exc:
            return error_result("downgrade_belief", "INVALID_ARGUMENT", str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("downgrade_belief", exc)

    def detect_conflict(self, subject: str, predicate: str) -> dict[str, Any]:
        """Return active or disputed claims with different values.

        Inputs: subject and predicate. Output: conflicting Belief objects in a success
        envelope, or an empty list when the claims agree. Error codes:
        INVALID_ARGUMENT or STORAGE_ERROR.
        """
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or not isinstance(predicate, str)
            or not predicate.strip()
        ):
            return error_result(
                "detect_conflict",
                "INVALID_ARGUMENT",
                "subject and predicate must be non-empty",
            )
        try:
            items = self.database.list_active(subject, predicate)
            conflicts = find_conflicts(items)
            return success_result(
                "detect_conflict", [item.model_dump(mode="json") for item in conflicts]
            )
        except Exception as exc:  # noqa: BLE001
            return self._storage_error("detect_conflict", exc)

    def reset(self) -> dict[str, Any]:
        """Clear this memory instance for a reproducible run.

        Inputs: none. Output: `{\"reset\": true}` in a success envelope. Error codes:
        STORAGE_ERROR.
        """
        try:
            self.database.reset()
            self.graph.clear()
            return success_result("reset_memory", {"reset": True})
        except Exception as exc:
            logger.exception("Failed to reset belief memory")
            return error_result(
                "reset_memory", "STORAGE_ERROR", str(exc), retryable=True
            )

    def close(self) -> None:
        """Close this memory's database connection."""
        self.database.close()

    def snapshot(self) -> dict[str, Any]:
        """Return the current graph nodes and edges as JSON-compatible data."""
        return {
            "nodes": [
                dict(attributes) for _, attributes in self.graph.nodes(data=True)
            ],
            "edges": [
                {"from": source, "to": target, **attributes}
                for source, target, attributes in self.graph.edges(data=True)
            ],
        }
