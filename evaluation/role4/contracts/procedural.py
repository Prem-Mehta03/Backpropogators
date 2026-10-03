"""Role 2 entry point and instrumented tool access supplied by Role 4."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from evaluation.role4.contracts.events import ResponseMetadata


class ToolExecutor(Protocol):
    def call(self, name: str, arguments: dict) -> dict: ...


@dataclass
class QueryContext:
    tools: ToolExecutor
    subject: str
    predicate: str
    max_steps: int = 8


@runtime_checkable
class ProceduralPort(Protocol):
    def reset(self, scenario_id: str) -> None: ...
    def run_query(self, query: str, context: QueryContext) -> ResponseMetadata: ...
