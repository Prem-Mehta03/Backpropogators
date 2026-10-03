> Historical Phase 1–3 Role 4 reference design, adapted for this clone. These ports are internal evaluation fixtures, not approved Vyom-owned shared contracts or measured teammate integration. See phase_a_alignment.md and teammate_inputs.md.

# Shared integration contracts — Phases 2 through 4

**Owner:** Role 4. **Status:** implemented and exercised with deterministic reference layers; pending teammate review. No real teammate modules were found. Phase 2 demonstrates S01; Phase 3 adds S02, S03, S04, S05 and S08; Phase 4 adds S06, S07, S09 and S10 through the same adapters.

## Responsibilities and dependencies

Role 1 owns declarative beliefs, provenance, persistence and memory APIs. Role 2 owns reasoning, tool choice, the execution entry point and response metadata. Role 3 owns the mock environment, sensor observations, resets, revisions and later movement. Role 4 owns these interfaces, dictionary-to-model adapters, boundary instrumentation, run construction, evaluation and artifacts.

Shared ports use `typing.Protocol` with runtime structural checks. Those checks confirm method presence only; the adapters perform payload validation. The existing Phase 1 `BeliefState`, `SensorReading`, `Event`, update/response events, `TestRunRecord` and `EvaluationResult` are reused. `SensorObservation` wraps the existing reading with unit and revision metadata; `BeliefRevision` adds before/after states and evidence references.

## Declarative operations

| Operation | Input | Canonical adapter output | Public dictionary backend return |
| --- | --- | --- | --- |
| `reset(scenario_id)` | Nonempty registered scenario ID | None | None; clear previous run and restore fixture baseline |
| `get_beliefs(subject, predicate)` | Two nonempty strings; exact, case-sensitive identifiers | Detached list of BeliefState | List of belief dictionaries; empty list when no match |
| `get_belief_snapshot()` | None | Complete detached list of BeliefState | All current records in stable order, with unique belief IDs |
| `upsert_belief(belief, evidence_references)` | Valid BeliefState and nonempty unique evidence-ID list | BeliefRevision | Object with `before`, `after`, `evidence_refs` |
| `get_belief_history(subject, predicate)` | Same query keys | Ordered list of BeliefRevision | List of the same revision dictionaries; empty list when no history |

Each belief requires `belief_id`, `subject`, `predicate`, JSON `value`, `perspective`, `source`, `confidence`, and `observed_at`. Source is a nonempty string or explicit null; null means provenance is unknown, not trusted. Unknown JSON metadata is preserved in adapter debug data, without becoming an evaluation field.

A new belief has `before: null`. Updating a current belief returns its complete previous state, including the previous value, and retains an immutable revision in history. Seeded initial history entries may have empty evidence references; actual upserts require references. The adapter checks receipts against public before/after snapshots, requires the requested state to be committed and rejects unrelated snapshot changes. It does not read a database or private backend fields.

The same belief ID cannot change subject, predicate or perspective. Existing historical beliefs are immutable through this adapter; record a new current observation under another ID. In S01, `path_a_map` remains historical clear and `path_a_sensor` becomes agent_sensor blocked. The brief's display name “path_A” uses the existing registry's canonical subject `path_a`; identifiers are not silently case-normalized.

## Sensorimotor operations

| Operation | Input | Canonical output | Public backend return |
| --- | --- | --- | --- |
| `reset(scenario_id)` | Registered scenario ID | None | Restore initial state and revision deterministically |
| `read_lidar()` | None | SensorObservation | Reading dictionary with unit and revision |
| `read_camera()` | None | SensorObservation | Same schema; explicit unavailable error when absent |
| `get_environment_state()` | None | Detached JSON object | `fixture_time`, integer `revision`, list `readings`, optional scenario metadata |
| `get_environment_revision()` | None | Positive integer | Current revision; booleans/floats are rejected |

Sensor payloads require all existing SensorReading fields: `reading_id`, `sensor`, `subject`, `predicate`, JSON `value`, `confidence`, `observed_at`, and object `details`. They also require `unit` (a string, or null when no unit applies) and positive integer `environment_revision`. `reading_id` is the evidence ID, exposed as `SensorObservation.evidence_id`; no duplicate ID field is needed.

A LiDAR observation can have categorical value `blocked` and `details.distance_cm: 12`. Such a detail requires `unit: "cm"` and a nonnegative finite number. Camera color can use `unit: null`. The read method rejects the wrong sensor name and requires the reading revision to equal the current public environment revision. Initial environment snapshots retain the existing scenario format: their embedded Phase 1 readings do not need the additional top-level unit/revision fields; those are required on actual sensor returns.

Revision starts at a positive integer and advances when state changes. Re-observation after change must produce a new evidence ID. Adapters check equality between a returned observation and current revision, including embedded revision metadata when present. Phase 3 checks static revision and simulated observation age; Phase 4 replays the deterministic S10 change and requires revalidation. General concurrent changes remain future work.

## Procedural operations

| Operation | Input | Output |
| --- | --- | --- |
| `reset(scenario_id)` | Registered scenario ID | None; prepare a new run |
| `run_query(query, context)` | Nonempty query and QueryContext | ResponseMetadata, converted from public response dictionary |

QueryContext holds `tools`, `subject`, `predicate` and a positive `max_steps` (default 8). It contains input identifiers and instrumented tool access, not the expected outcome or pass criteria. The backend must call `context.tools.call(name, arguments)` for observable tool work. The dispatcher records the call before invoking an adapter and the validated result immediately after it returns.

S01 supports these tool names:

| Name | Arguments | Return |
| --- | --- | --- |
| `query_memory` | `subject`, `predicate` | Canonical `beliefs`, `evidence` and public `raw` return |
| `read_lidar` / `read_camera` | Empty object | Canonical `observation`, `evidence` and `raw` |
| `update_belief` | `belief`, `evidence_refs` | Committed `belief`, `before`, `evidence_refs`, empty `evidence` list and `raw` |

The maximum-step limit counts tool invocations. When exhausted, the next tool is not invoked and the run aborts as a contract error. It is not an execution-time limit and cannot stop arbitrary non-tool computation. The eventual LLM implementation must also bound its reasoning loop.

ResponseMetadata requires `text`, unique `evidence_refs` (possibly empty), object `claims`, and boolean `acknowledge_conflict`, `acknowledge_uncertainty`, `acknowledge_missing`. The adapter validates it; the recorder rejects unknown evidence references, pending tool results and a second final response. Text and metadata both remain in the trace for human review. Automated semantic agreement between prose and metadata is not implemented.

Phase 3 adds backward-compatible optional `claim_support` and `public_reasons` lists. Each support record requires nonempty `claim_key`, `evidence_id`, `perspective`, JSON `value`, `source` (nonempty string or explicit null) and finite confidence in [0, 1]. A support record binds a factual claim to an actually returned evidence item. The Phase 3 evaluator requires these bindings for policy-declared factual keys and checks value, target, source, perspective and confidence. Derived decision claims use separate policy checks. `public_reasons` contains short observable explanations, never hidden reasoning. Empty optional lists are omitted when serializing older responses. The pending human worksheet is documented in [reference_response_review_rubric.md](reference_response_review_rubric.md).

```json
{"claim_key":"path_status","value":"clear","evidence_id":"lidar_clear","perspective":"agent_sensor","source":"lidar","confidence":0.97}
```

## Evidence, calls and trace policies

Evidence items contain a nonempty `evidence_id`, `category` and nonempty structured `data` object. Data is the actual canonical return, not a verbal summary. IDs are unique per run and deterministic for the reference demo. Memory evidence IDs include the call ID and belief ID. Sensor evidence IDs come from the layer. A repeated observation must use a fresh ID even if its value is unchanged. References may only cite evidence already returned.

Memory categories map user records to `user`, retain `stored_map`/`stored_record` sources, map other historical records to `historical`, and otherwise use the source or `unverified_memory`. Sensor categories use the sensor name (`lidar` or `camera`). The original source remains in evidence data even when the category is broader. These Phase 3 conventions still need teammate review. Evidence is trusted instrumented input, not cryptographically authenticated.

Call IDs are nonempty, unique within a run and generated as `call_001`, `call_002`, etc. Every result or error must match a pending call ID and tool name. Duplicate call/evidence IDs and unmatched results raise ContractError before being accepted. Tool errors preserve valid JSON raw payloads; non-JSON raw values are represented by a type/note object so error logging still works.

Event envelopes reuse Phase 1: UTC `timestamp`, `event_type`, `scenario_id`, object `payload`. Execution events include input snapshots, calls, results, belief updates and one response. Update events follow the committed update return and contain the actual receipt and call ID. On a contract failure, `tool_error` (when applicable) and `contract_error` retain the partial trace; no successful result, fabricated final response or evaluation result is added.

Phase 3 additionally wraps public backend operations with `boundary_call` and `boundary_result`, paired by unique `boundary_###` IDs. Calls store public request arguments; returns store public response data or an error. Each carries source layer, overall `backend_type` and state (`requested`, `returned`, `error`). Instrumented tool events carry source layer and state (`requested`, `success`, `rejected`, `error`). Initial snapshots keep the original envelope format; the run's `integration_metadata` stores the overall reference/real/mixed label, per-layer labels, execution policy, independent expected policy, injected fault and pending human-review status. Confidence, perspective, observation time and revision remain in their applicable returned data.

Forbidden `move_forward` attempts are recorded and rejected by the Phase 3 gateway before backend invocation. They still fail the forbidden-action evaluator check. No movement API is implemented. Public query-context logging includes subject, predicate and maximum steps; it excludes tool objects, expected assertions and private reasoning.

## Time and confidence policies

Observation timestamps must be ISO 8601 with an explicit timezone. Adapters normalize observations to UTC and reject missing, malformed or timezone-naive times. Event/evaluation timestamps use the existing UTC clock. Fixed fixture observation times model the scenario's simulated time; they are not fresh wall-clock measurements.

Confidence is a finite number from 0 through 1; booleans and numeric strings are rejected. Adapters preserve confidence, without inventing a confidence fusion rule or recalibrating it. Phase 3 defaults to minimum sensor confidence 0.7 and maximum observation age 300 simulated seconds, configured in `tests/role4/phase3_policies.json`. These evaluation choices still require team agreement. Observation age is measured against `fixture_time`; the fixture does not claim current real-world sensing.

Perspective values are `user`, `historical`, `agent_sensor` and `agent_sensor:<sensor>`. Separate IDs retain conflicting claims. Evidence updates do not globally replace every claim about a subject.

## Errors and evaluation path

Malformed boundary data raises ContractError with the operation/field named. Missing sensors raise SensorUnavailable, a ContractError subclass. Reference resets reject unsupported scenario IDs. Empty memory/history queries return empty lists. There are no fabricated default readings, silent ID repairs or automatic recovery. Backend programming errors outside the documented contract are allowed to surface rather than being reported as an ordinary scenario failure.

The adapter cannot roll back a teammate's dishonest or broken commit; it detects receipt/snapshot mismatches and aborts evaluation. Teammate writes must be transactional and reset must isolate runs. Current integration assumes serialized operations; concurrent writes need an agreed snapshot/transaction policy.

The runner resets all three backends, captures public initial snapshots, executes via ProceduralAdapter, records its validated response and captures the final memory snapshot. It builds TestRunRecord from these observed events and states, then calls the existing evaluator. Optional Phase 3 policy checks extend that evaluator while preserving the Phase 1/2 check counts. Results and JSONL use the existing logger. Contract-error executions bypass evaluation entirely.

The event's `execution: "integrated"` means the contract path was executed. The Phase 2 summary separately records `layer_source: "reference_layers"` and `teammate_modules_integrated: false`; it does not claim real teammate integration.

## Compact examples from the valid reference run

These examples are generated from the Phase 2 demonstration. Times may differ in future runs.

### Stored clear-path belief

```json
{"belief_id":"path_a_map","confidence":0.85,"observed_at":"2026-10-02T08:59:00+00:00","perspective":"historical","predicate":"status","source":"stored_map","subject":"path_a","value":"clear"}
```

### Blocked LiDAR observation at 12 cm

```json
{"confidence":0.98,"details":{"distance_cm":12},"environment_revision":1,"observed_at":"2026-10-02T09:00:00+00:00","predicate":"status","reading_id":"lidar_evidence","sensor":"lidar","subject":"path_a","unit":"cm","value":"blocked"}
```

### Memory query tool call

```json
{"event_type":"tool_call","payload":{"arguments":{"predicate":"status","subject":"path_a"},"call_id":"call_001","tool_name":"query_memory"},"scenario_id":"S01","timestamp":"2026-10-01T19:49:55.318474+00:00"}
```

### Memory query tool return

```json
{"event_type":"tool_result","payload":{"beliefs":[{"belief_id":"path_a_map","confidence":0.85,"observed_at":"2026-10-02T08:59:00+00:00","perspective":"historical","predicate":"status","source":"stored_map","subject":"path_a","value":"clear"}],"call_id":"call_001","evidence":[{"category":"stored_map","data":{"belief_id":"path_a_map","confidence":0.85,"observed_at":"2026-10-02T08:59:00+00:00","perspective":"historical","predicate":"status","source":"stored_map","subject":"path_a","value":"clear"},"evidence_id":"call_001:memory:path_a_map"}],"raw":[{"belief_id":"path_a_map","confidence":0.85,"observed_at":"2026-10-02T08:59:00+00:00","perspective":"historical","predicate":"status","source":"stored_map","subject":"path_a","value":"clear"}],"tool_name":"query_memory"},"scenario_id":"S01","timestamp":"2026-10-01T19:49:55.318600+00:00"}
```

### Committed belief update

```json
{"event_type":"belief_update","payload":{"after":{"belief_id":"path_a_sensor","confidence":0.98,"observed_at":"2026-10-02T09:00:00+00:00","perspective":"agent_sensor","predicate":"status","source":"lidar","subject":"path_a","value":"blocked"},"before":null,"call_id":"call_003","evidence_refs":["lidar_evidence"],"operation":"upsert"},"scenario_id":"S01","timestamp":"2026-10-01T19:49:55.319348+00:00"}
```

### Final structured response

```json
{"event_type":"agent_response","payload":{"acknowledge_conflict":true,"acknowledge_missing":false,"acknowledge_uncertainty":false,"claims":{"movement_safe":false,"path_status":"blocked"},"evidence_refs":["call_001:memory:path_a_map","lidar_evidence"],"raw":{"acknowledge_conflict":true,"acknowledge_missing":false,"acknowledge_uncertainty":false,"claims":{"movement_safe":false,"path_status":"blocked"},"evidence_refs":["call_001:memory:path_a_map","lidar_evidence"],"text":"The map reports clear; LiDAR observes blocked at 12 cm. The sources disagree; do not move forward."},"text":"The map reports clear; LiDAR observes blocked at 12 cm. The sources disagree; do not move forward."},"scenario_id":"S01","timestamp":"2026-10-01T19:49:55.319536+00:00"}
```

### Evaluation result (excerpt)

The full artifact contains 20 checks. This excerpt shows one successful check:

```json
{"scenario_id":"S01","run_id":"S01_integrated_valid","passed":true,"checks":[{"name":"response_claim:path_status","passed":true,"detail":"Response structured claim path_status must be 'blocked'"}],"failure_reasons":[],"evaluated_at":"2026-10-02T09:00:00+00:00"}
```

## Decisions needing teammate approval

Confirm operation names and dictionary mappings, canonical identifiers and perspective conventions, immutable historical records, source/category mapping, confidence meanings, observation time normalization, unit conventions, revision/change semantics, maximum steps, snapshot atomicity and final-response claims. These implemented contracts are proposals ready for review, not approval attributed to the other members.

Role 4 can replace the reference_backends factory with teammate backends passed to `run_s01`. If their public API differs, change only the relevant adapter mapping and its tests. Keep `evaluation/role4/reference_layers/` for deterministic regression tests. Never place evaluator checks inside a teammate implementation.

For Phase 3, inject the same three public backend objects through `run_scenario(..., memory_backend=..., procedural_backend=..., sensor_backend=..., backend_type="real")`. Mixed substitution requires explicit per-layer labels. Known references cannot be labelled real, and an unspecified real layer is rejected. The [Phase 3 evaluation plan](reference_phase3_evaluation_plan.md) lists the exact parameters and replacement points. All delivered Phase 3 artifacts remain `reference`; no teammate approval or integration is implied.
