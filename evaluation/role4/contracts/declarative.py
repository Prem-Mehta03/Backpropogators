"""Role 1 interface and committed before/after update receipt."""

from dataclasses import dataclass, asdict
from typing import Protocol, runtime_checkable
from evaluation.role4.models import BeliefState


@dataclass
class BeliefRevision:
    before: BeliefState | None
    after: BeliefState
    evidence_refs: list[str]

    def to_dict(self):
        return asdict(self)


@runtime_checkable
class DeclarativePort(Protocol):
    def reset(self, scenario_id: str) -> None: ...
    def get_beliefs(self, subject: str, predicate: str) -> list[BeliefState]: ...
    def get_belief_snapshot(self) -> list[BeliefState]: ...
    def upsert_belief(self, belief: BeliefState, evidence_references: list[str]) -> BeliefRevision: ...
    def get_belief_history(self, subject: str, predicate: str) -> list[BeliefRevision]: ...
