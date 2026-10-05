"""In-memory public dictionary API for integration testing only."""

from copy import deepcopy
from evaluation.role4.contracts.events import ContractError


class DeclarativeReference:
    def __init__(self, scenario_id, initial_beliefs):
        self.scenario_id = scenario_id
        self.initial = [b.to_dict() for b in initial_beliefs]
        self.reset(scenario_id)

    def reset(self, scenario_id):
        if scenario_id != self.scenario_id:
            raise ContractError(f"Memory reference supports only {self.scenario_id}")
        self._beliefs = {b["belief_id"]: deepcopy(b) for b in self.initial}
        self._history = [{"before": None, "after": deepcopy(b), "evidence_refs": []} for b in self.initial]

    def get_beliefs(self, subject, predicate):
        return [deepcopy(b) for b in self._beliefs.values() if b["subject"] == subject and b["predicate"] == predicate]

    def get_belief_snapshot(self):
        return deepcopy(list(self._beliefs.values()))

    def upsert_belief(self, belief, evidence_references):
        receipt = {"before": deepcopy(self._beliefs.get(belief["belief_id"])), "after": deepcopy(belief), "evidence_refs": list(evidence_references)}
        self._beliefs[belief["belief_id"]] = deepcopy(belief)
        self._history.append(deepcopy(receipt))
        return receipt

    def get_belief_history(self, subject, predicate):
        return [deepcopy(item) for item in self._history if item["after"]["subject"] == subject and item["after"]["predicate"] == predicate]
