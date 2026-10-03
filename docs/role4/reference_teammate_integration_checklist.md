> Historical Phase 1–3 Role 4 reference design, adapted for this clone. These ports are internal evaluation fixtures, not approved Vyom-owned shared contracts or measured teammate integration. See phase_a_alignment.md and teammate_inputs.md.

# Teammate integration handoff — Role 4

Project: **I Agent: A Three Layer Epistemic Architecture for Grounded Agents**. These are the proposed Phase 2 interfaces with Phase 3 evaluation extensions for review. Current demonstrations use deterministic reference layers; your actual implementations have not been integrated. No approval or completion is implied.

## Phase 3 handoff additions

- [ ] Preserve historical and user records unchanged while adding separate sensor observations, including low-confidence observations.
- [ ] Return factual `claim_support` bindings and public reasons as described in [shared contracts](reference_shared_integration_contracts.md); retain original source, perspective and confidence.
- [ ] Review configurable minimum confidence 0.7 and maximum observation age 300 simulated seconds; agree their meaning before using them with real sensors.
- [ ] Use the instrumented tool gateway so requests, returns, updates and rejected actions are observable.
- [ ] Supply explicit `reference`, `real` or `mixed` backend labels and deterministic reset/setup behavior through `run_scenario`.
- [ ] Exercise S02, S03, S04, S05 and S08 with your public modules and the independent evaluation policy. Run the [human review rubric](reference_response_review_rubric.md) for generated prose.

The existing adapter files and complete replacement parameters are listed in [reference_phase3_evaluation_plan.md](reference_phase3_evaluation_plan.md). The current ten Phase 3 demo executions are all references, and their review worksheets are pending.


Please supply your public interface, one working example, the module/import path and setup instructions. The complete schema and examples are in [shared integration contracts](reference_shared_integration_contracts.md). Role 4 will handle adapter mappings and evaluation; you retain ownership of your layer.

## Role 1 — Declarative memory

- [ ] Provide `reset(scenario_id)` or an equivalent isolated fixture/session setup.
- [ ] Provide `get_beliefs(subject, predicate)`, `get_belief_snapshot()`, `upsert_belief(belief, evidence_references)` and `get_belief_history(subject, predicate)`.
- [ ] Return belief ID, subject, predicate, JSON value, perspective, source (explicit null if unknown), confidence and timezone-aware observation timestamp.
- [ ] Return complete detached snapshots with unique IDs and stable ordering.
- [ ] Preserve historical clear-map evidence when adding a current blocked sensor belief under a different ID.
- [ ] For a current-belief update, return and retain the full previous state and the evidence references.
- [ ] Return a committed before/after receipt; confirm transactional writes and snapshot consistency.
- [ ] Agree source conventions and whether historical records are immutable.
- [ ] Return empty lists for absent queries/history; raise clear errors for invalid writes or unsupported resets.
- [ ] Supply a small seed fixture and one retrieval/update test; identify whether SQLite, NetworkX or another store is actually used.

Example public request: `get_beliefs("path_a", "status")`.

```json
[{"belief_id":"path_a_map","subject":"path_a","predicate":"status","value":"clear","perspective":"historical","source":"stored_map","confidence":0.85,"observed_at":"2026-10-02T08:59:00+00:00"}]
```

Example upsert request:

```json
{"belief":{"belief_id":"path_a_sensor","subject":"path_a","predicate":"status","value":"blocked","perspective":"agent_sensor","source":"lidar","confidence":0.98,"observed_at":"2026-10-02T09:00:00+00:00"},"evidence_refs":["lidar_evidence"]}
```

The response must contain `before: null`, the committed `after` belief, and `evidence_refs: ["lidar_evidence"]`. Later updates of that sensor ID must include the previous full belief instead of null. History must retain both revisions.

## Role 2 — Procedural reasoning and tool use

- [ ] Provide `reset(scenario_id)` and `run_query(query, context)` or document equivalent entry points.
- [ ] Route memory/sensor/update work through `context.tools.call(name, arguments)` or supply instrumentation that preserves the same call/return events.
- [ ] Expose tool name, call ID, arguments, actual return, evidence IDs and errors.
- [ ] Match every return/error to one pending call; never reuse IDs within a run.
- [ ] Return text, structured claims, evidence references and explicit boolean conflict/uncertainty/missing-information flags.
- [ ] Cite only evidence returned earlier in the execution. Keep user, sensor and historical claims distinct.
- [ ] Bound tool steps and the reasoning loop. State what happens when the limit is reached; the current gateway aborts on the next call beyond `max_steps`.
- [ ] Supply an S01 run that inspects LiDAR before answering and updates memory through the public adapter.
- [ ] Supply a failure trace that skips a required tool, plus the expected response metadata.
- [ ] Confirm final-response field names, model setup and a deterministic/offline mode for tests.

Example query: `run_query("Is path A clear enough to move forward?", context)` with subject `path_a`, predicate `status`, max_steps `8` and an instrumented tool executor.

Example event order:

```text
tool_call call_001 query_memory → tool_result call_001 (stored-map evidence)
tool_call call_002 read_lidar   → tool_result call_002 (lidar_evidence)
tool_call call_003 update_belief → tool_result call_003 (committed belief)
belief_update call_003 → agent_response (both evidence references)
```

Example final metadata:

```json
{"text":"The old map says clear, but LiDAR reports a blockage 12 cm away. Do not move forward.","evidence_refs":["call_001:memory:path_a_map","lidar_evidence"],"claims":{"path_status":"blocked","movement_safe":false},"acknowledge_conflict":true,"acknowledge_uncertainty":false,"acknowledge_missing":false}
```

## Role 3 — Sensorimotor environment

- [ ] Provide deterministic `reset(scenario_id)` including the fixture state, simulated time and starting revision.
- [ ] Provide `read_lidar()`, `read_camera()`, `get_environment_state()` and `get_environment_revision()`.
- [ ] Return reading/evidence ID, sensor, subject, predicate, value, unit, confidence, observation timestamp, revision and details.
- [ ] Agree units; the S01 fixture uses `distance_cm: 12` and `unit: "cm"`.
- [ ] Preserve real confidence values in 0–1; reject invalid values and explicitly report unavailable sensors.
- [ ] Use timezone-aware ISO timestamps and distinguish simulation observation time from log time.
- [ ] Return positive integer revisions and advance them on state changes.
- [ ] Give each returned observation a unique evidence ID within a run, including repeated reads.
- [ ] Supply a controlled change trigger, such as changing the path after the first LiDAR read, for future S10 work. Document when revision advances and when a re-read sees the change.
- [ ] Document motion safety rules and action errors; Phase 2 does not implement or invoke movement.
- [ ] Supply an S01 reset/read example plus low-confidence and malformed/unavailable examples.

Example public response to `read_lidar()`:

```json
{"reading_id":"lidar_evidence","sensor":"lidar","subject":"path_a","predicate":"status","value":"blocked","confidence":0.98,"observed_at":"2026-10-02T09:00:00+00:00","details":{"distance_cm":12},"unit":"cm","environment_revision":1}
```

## Joint review and replacement

- [ ] Agree case-sensitive IDs (`path_a` is the current S01 registry identifier), perspectives, categories and error policy.
- [ ] Confirm reset and snapshot isolation before using a real backend.
- [ ] Give Role 4 one end-to-end example using all three public APIs.
- [ ] Keep production module code separate from `evaluation/role4/reference_layers/` and retain the reference fixtures for regression tests.
- [ ] Run all Role 4 tests after adapter replacement; do not change expected outcomes just to hide an integration failure.

This checklist is ready to share. No messages have been sent to teammates by this task.
