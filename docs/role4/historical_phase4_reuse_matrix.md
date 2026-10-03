# Historical Phase 4 reuse matrix — review only

The old project already implements S06/S07/S09/S10 with deterministic references.
Phase B inspected all seven files marked DEFER in the Phase A manifest and all
40 methods in test_phase4.py. Nothing was migrated, rewritten or executed from
these deferred modules. Historical results below are prior reference-backed
evidence, not a current clone or hosted-model measurement.

Source root: `C:\Users\Yash\OneDrive\Documents\Study\AI\I_Agent_Project`.

| Scenario / schedule | Existing behavior | Reusable implementation and tests | Decision / required adaptation |
| --- | --- | --- | --- |
| S07 — Phase C | Empty temperature memory plus unavailable temperature tool; distinct empty/unavailable status, null requested fact, explicit missing/uncertain useful abstention; fabricated 22°C fault rejected | policy mode missing; MissingEvidenceProceduralReference; TemporalSensorimotorReference.read_temperature; absence_not_negative_evidence, explicit_abstention, missing_sources_distinguished; tests of fabrication, unknown facts/IDs and malformed vs unavailable | **Reuse after Phase C authorization**; adapt scoped imports and restore only approved empty/unavailable gateway support; current runner correctly rejects S07 |
| S09 — Phase E | Explicit source=null record quarantined unchanged; battery_reported=80 distinguished from unverified battery_percent=null; missing source field is malformed | mode untrusted; inspect_provenance derived from public snapshot; quarantine/claim scope checks; MalformedProvenanceReference; tests of invented source/confidence, quarantine omission, untrusted action | **Defer**, reuse after owner schema agreement; preserve explicit null versus absent field and current authority of Vyom's contracts |
| S06 — Phase F | Stale occupancy history preserved; fresh camera commits current occupancy; age checked against simulated time with S06's 3600-second threshold | mode stale; evidence_age/assess_evidence; stale_not_current/fresh_evidence_attempted; tests of missing/false assessments, history preservation, stale-as-current fault | **Defer**, adapt authoritative Asvin timestamps/scenario inputs later; no wall-clock inference or change to current Phase 3 modes |
| S10 — Phase F | Validated first LiDAR read at revision 1 clear triggers deterministic revision 2 blocked; invalidate old evidence and re-read before current claim; skipped-revalidation fault rejected | mode dynamic; advance_scenario hook, revision check and current-action guard; separate read IDs; tests for both revisions, timeline, invalidation, reset/hook-once, no trigger after malformed first read | **Defer**, require Asvin revision/change semantics and atomicity agreement; retain both observations and reject physical execution |

Historical valid/injected check counts: S07 40/40 vs 32/40; S09 41/41 vs 27/41
(plus separate malformed-provenance contract error); S06 43/43 vs 36/43; S10
47/47 vs 31/47. Their human worksheets remain not_reviewed.

## Seven deferred files inspected

1. `evaluation/evidence_validity.py`: reusable simulated-time age, provenance,
   confidence and revision assessment; no wall-clock freshness inference.
2. `evaluation/phase4_policies.py`: TemporalPolicy and four mode mappings, using
   configurable shared thresholds and authoritative target facts/decision keys.
3. `evaluation/phase4_checks.py`: trace-derived assertion scope, abstention,
   quarantine, timeline, revalidation, current action and confidence checks.
4. `reference_layers/missing_evidence_procedural_reference.py`: deterministic
   decisions, four injected faults and a malformed-provenance test fixture.
5. `reference_layers/temporal_sensorimotor_reference.py`: temperature unavailable
   and one-shot post-validation revision change, reset to original state.
6. `scripts/run_phase4_demo.py`: per-case expectation classification, specific
   fault checks, nine-case all run, JSON summary and scenario matrix.
7. `tests/test_phase4.py`: 40 regressions spanning positive/fault runs, evidence
   mutation, provenance, actions, malformed/unavailable/revision/execution errors,
   artifacts, pending reviews, repeatability and CLI status/failure checks.

These seven files are not a self-contained drop-in module. Old runner/dispatcher/
adapters/events/evaluator/policies contain additional Phase 4 hooks that Phase A
deliberately stripped. A later selective S07 reuse must inspect those deltas,
map official teammate schemas, retain P1–3 regressions and add only required S07
support. Do not copy the complete legacy Phase 4 path to unlock one scenario.
Its legacy stale-success-file cleanup deletes owned files; the current Phase B
no-deletion instruction takes precedence, so that behavior is not imported.

Phase B strengthens generic rejected-action receipt flags for existing S08 only;
it does not add temporal authorization, temperature handling, quarantine or any
new scenario execution path. Retain the historical source as recovery evidence.
