"""Validate the public query response; tool observations come from the context."""

from copy import deepcopy
from evaluation.role4.contracts.events import ContractError, ResponseMetadata, nonempty


class ProceduralAdapter:
    def __init__(self, backend):
        self.backend = backend
        self.last_raw = None

    def reset(self, scenario_id):
        self.backend.reset(nonempty(scenario_id, "scenario_id"))
        self.last_raw = None

    def run_query(self, query, context):
        nonempty(query, "query")
        if isinstance(context.max_steps, bool) or not isinstance(context.max_steps, int) or context.max_steps < 1:
            raise ContractError("max_steps must be a positive integer")
        raw = self.backend.run_query(query, context)
        self.last_raw = deepcopy(raw.to_dict() if isinstance(raw, ResponseMetadata) else raw)
        return ResponseMetadata.from_payload(raw)
