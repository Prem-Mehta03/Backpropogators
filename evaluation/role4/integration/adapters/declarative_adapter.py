"""Convert and verify Role 1's public dictionary API."""
from copy import deepcopy
from evaluation.role4.contracts.declarative import BeliefRevision
from evaluation.role4.contracts.events import ContractError, belief_from_payload, references, nonempty
from evaluation.role4.models import require_fields

class DeclarativeAdapter:

    def __init__(self, backend):
        self.backend = backend
        self.last_raw = None

    def reset(self, scenario_id):
        self.backend.reset(nonempty(scenario_id, 'scenario_id'))
        self.last_raw = None

    def _beliefs(self, raw):
        if not isinstance(raw, list):
            raise ContractError('Memory response must be a list of beliefs')
        beliefs = [belief_from_payload(item) for item in raw]
        if len({b.belief_id for b in beliefs}) != len(beliefs):
            raise ContractError('Duplicate belief IDs in memory response')
        self.last_raw = deepcopy(raw)
        return beliefs

    def get_beliefs(self, subject, predicate):
        nonempty(subject, 'subject')
        nonempty(predicate, 'predicate')
        beliefs = self._beliefs(self.backend.get_beliefs(subject, predicate))
        if any((b.subject != subject or b.predicate != predicate for b in beliefs)):
            raise ContractError('Memory query returned beliefs for another subject/predicate')
        return beliefs

    def get_belief_snapshot(self):
        return self._beliefs(self.backend.get_belief_snapshot())

    def _revision(self, raw):
        try:
            require_fields(raw, {'before', 'after', 'evidence_refs'}, 'belief revision')
            before = belief_from_payload(raw['before']) if raw['before'] is not None else None
            after = belief_from_payload(raw['after'])
            refs = references(raw['evidence_refs'], allow_empty=True)
            if before and (before.belief_id, before.subject, before.predicate, before.perspective) != (after.belief_id, after.subject, after.predicate, after.perspective):
                raise ValueError('Update changed belief identity or perspective')
            return BeliefRevision(before, after, refs)
        except (ValueError, TypeError) as exc:
            raise ContractError(f'Invalid belief revision: {exc}') from exc

    def upsert_belief(self, belief, evidence_references):
        belief = belief_from_payload(belief)
        refs = references(evidence_references)
        before_snapshot = {b.belief_id: b for b in self.get_belief_snapshot()}
        before = before_snapshot.get(belief.belief_id)
        if before:
            if (before.subject, before.predicate, before.perspective) != (belief.subject, belief.predicate, belief.perspective):
                raise ContractError('Upsert must preserve belief identity and perspective')
            if before.perspective == 'historical' and before != belief:
                raise ContractError('Historical belief is immutable; add a separate current belief ID')
        raw = self.backend.upsert_belief(belief.to_dict(), list(refs))
        receipt = self._revision(raw)
        if receipt.before != before or receipt.after != belief or receipt.evidence_refs != refs:
            raise ContractError('Committed update receipt does not match requested before/after state and evidence')
        after_snapshot = {b.belief_id: b for b in self.get_belief_snapshot()}
        expected = {**before_snapshot, belief.belief_id: belief}
        if after_snapshot != expected:
            raise ContractError('Committed memory snapshot differs from the update receipt or changed unrelated beliefs')
        self.last_raw = deepcopy(raw)
        return receipt

    def get_belief_history(self, subject, predicate):
        raw = self.backend.get_belief_history(nonempty(subject, 'subject'), nonempty(predicate, 'predicate'))
        if not isinstance(raw, list):
            raise ContractError('Belief history must be a list of revisions')
        history = [self._revision(item) for item in raw]
        if any((item.after.subject != subject or item.after.predicate != predicate for item in history)):
            raise ContractError('History returned another subject/predicate')
        self.last_raw = deepcopy(raw)
        return history
