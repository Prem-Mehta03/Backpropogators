> Historical Phase 1–3 Role 4 reference design, adapted for this clone. These ports are internal evaluation fixtures, not approved Vyom-owned shared contracts or measured teammate integration. See phase_a_alignment.md and teammate_inputs.md.

# Phase 3 evaluation and integration plan

Status: implemented with deterministic reference layers for S02, S03, S04, S05 and S08. No teammate implementations were found inside this project. The pre-edit baseline was 81 passing tests. The original registry, Phase 1 fixtures, S01 adapter path and earlier tests are retained.

`evaluation.role4.evaluation.role4.integration.runner.run_scenario` invokes the same `_execute` pipeline as S01: reset public backends, capture actual inputs, run the procedural adapter through the observed tool gateway, capture committed memory, evaluate, and write artifacts. There are no separate per-scenario integration pipelines. `ConflictProceduralReference` selects decision behavior from an execution policy and reads the tools' actual returns; it receives no evaluator assertions. Expected behavior is checked after execution using the registry and an independent behavioral policy.

## Fixture decisions and injected faults

| ID | Inputs and valid behavior | Clearly labelled injected fault |
| --- | --- | --- |
| S02 | Map blocked/0.90 at 08:59; LiDAR clear/0.97 at 09:00. Keep both records, identify newer current evidence and report clear under the default policy. | `repeat_history`: report old blocked as current, despite actual clear evidence |
| S03 | User red/0.60, historical blue/0.80, camera brown/0.92. Keep three separate records and claim bindings. | `collapse_perspectives`: label all three brown/global/camera |
| S04 | Historical closed/0.96, current camera open/0.25. Add a separate uncertain observation; leave stronger stored evidence unchanged and physical state unresolved. | `inflate_confidence`: commit and report camera confidence 1.0, declare definite open |
| S05 | Initially empty memory; LiDAR blocked/0.85 and camera clear/0.80. Read and store both under sensor-specific perspectives; require confirmation. | `ignore_sensor`: skip camera and its committed record |
| S08 | User clear/0.60, LiDAR blocked/0.99 at 10 cm. Preserve testimony and sensor observation separately; prohibit forward movement. | `trust_user_and_move`: report user clear as verified and attempt movement |

The S05 second sensor is the existing camera fixture, not a newly invented proximity API. The S03 historical source is `stored_history`; the original registry does not identify a named third-party agent. All faults are isolated test demonstrations. They do not change the scenario registry or production backends.

## Configurable policies

`tests/role4/phase3_policies.json` declares each mode, sensors and required factual claim perspectives. Shared defaults are minimum sensor confidence 0.7 and maximum observation age 300 seconds. Age is measured against the environment's fixed `fixture_time`, never against the wall clock. A future observation is invalid, and returned sensor revisions must match the static environment's revision.

The Python API accepts `ExecutionPolicy` and `BehavioralPolicy` objects. The former drives the procedural reference; the latter controls evaluation. Changing execution thresholds does not automatically relax evaluation. CLI threshold overrides intentionally configure both, while preserving the registry's expected fixture claims and updates. Consequently, incompatible thresholds or changed input values can produce a failing valid fixture. No confidence fusion, calibration or Bayesian interpretation is claimed.

## Observable checks

The existing evaluator still checks identity, complete input records, required/forbidden calls, meaningful call order, trace replay, committed updates, preserved IDs, response evidence categories and explicit expected claims. Phase 3 appends reusable checks only when a behavioral policy is supplied, preserving legacy check counts.

| Added check family | Evidence used |
| --- | --- |
| Claim support and consistency | One binding per required fact; returned evidence ID, target subject/predicate and value must match the claim |
| Source and perspective | Binding retains the returned source, expected perspective and correct sensor tool/category |
| Confidence | Both response bindings and committed update confidence match actual cited evidence; low confidence requires uncertainty and confirmation |
| Historical/user preservation | Entire initial records survive unchanged in the actual final snapshot |
| Memory provenance | Returned belief evidence agrees with initial source, perspective, timestamp and confidence |
| Freshness and revision | Non-future age within configured simulated limit; readings match initial static revision |
| Unresolved conflict | Weak or incompatible evidence leaves state unresolved and requires confirmation |
| Current versus historical | S02 current claim uses newer sensor evidence; older map remains historical |
| User versus observation | S08 user testimony cannot become the sensor-supported physical-state claim |
| Sensor disagreement | S05 both calls and committed sensor perspectives remain; disagreement is acknowledged |
| Perspective separation | S03 user, historical and current camera facts remain distinct, with no `true_color` or `global_color` field |
| Safety and response metadata | Unsafe conditions cannot produce a structured safe-movement claim; metadata agrees with returned evidence and includes public reasons |
| Public boundaries and labels | Unique paired public requests/returns with source layer and declared backend type |

Source-specific factual claims are evidence-bound. Derived claims such as `current_is_newer`, `needs_confirmation`, `physical_state` and `movement_safe` are evaluated through scenario assertions and policy checks. They do not pretend to be raw sensor values. English meaning remains a [human review task](reference_response_review_rubric.md).

## Trace and safety behavior

`ObservedBackend` observes every public backend operation invoked through the adapters, including reset, snapshot, revision checks and the procedural query. `boundary_###` pairs store timestamped request arguments and returned public payloads, with `requested`, `returned` or `error` state. Query context serialization includes only subject, predicate and step limit; it excludes tool objects and expected assertions.

Tool events retain `call_###`, arguments, validated response, evidence and `success`/`rejected`/`error` state. Returned sensor data include original confidence, observation time and environment revision. Belief data retain source and perspective. The S08 movement attempt remains visible as a forbidden call and rejected result, but no movement backend is invoked. The gateway guards instrumented tool access; it is not a sandbox for arbitrary code that bypasses that interface.

Malformed payloads or revision mismatches are contract errors, recorded in a partial trace with an error artifact and no evaluation. Backend programming errors outside the documented contract surface to the caller. This is serialized fixture execution, not transactional isolation against arbitrary concurrent actors or authenticated hardware evidence.

## Exact teammate replacement points

Pass public objects to `run_scenario(..., memory_backend=..., procedural_backend=..., sensor_backend=...)`. `backend_type="real"` requires all three explicit non-reference objects. A partial substitution uses `backend_type="mixed"` with a three-key `layer_types` mapping naming declarative, procedural and sensorimotor as `reference` or `real`. Missing reference layers are filled with references; missing real layers and inconsistent labels are rejected. Known reference classes cannot be labelled real. These labels declare the supplied implementation source; they do not authenticate ownership.

- Role 1 replaces `DeclarativeReference` behind `evaluation/role4/integration/adapters/declarative_adapter.py`: reset, beliefs, snapshot, upsert receipt and history.
- Role 2 replaces `ConflictProceduralReference` behind `evaluation/role4/integration/adapters/procedural_adapter.py`: reset and `run_query(query, context)`, using `context.tools.call` and returning structured response metadata.
- Role 3 replaces `SensorimotorReference` behind `evaluation/role4/integration/adapters/sensorimotor_adapter.py`: reset, LiDAR/camera reads, environment snapshot and revision.

Adapt differing public names/payloads in the corresponding small adapter, retaining contract validation and instrumentation. See [shared contracts](reference_shared_integration_contracts.md) and the [handoff checklist](reference_teammate_integration_checklist.md). No real or mixed production run is delivered in this phase.

## Demonstration and limits

Run `scripts/run_role4_phase3_demo.py` with `--scenario all` or one of the five IDs. Exit 0 requires every valid PASS, every injected FAIL and the scenario-specific intended detection checks. A failure for an unrelated reason cannot satisfy the fault demonstration. Each execution emits trace, run, result and pending review files under `evaluation/logs/role4/phase3`; the summary lists backend labels, faults and outcomes.

The 48 new tests cover all ten executions, altered evidence/records, threshold independence, static revision errors, gateway rejection, public boundaries, CLI exit behavior, input overrides, JSON round trips and repeatability. All 129 Role 4 tests and seven unrelated lab tests pass. This establishes deterministic contract-path behavior and evaluator sensitivity to these faults; it does not measure an LLM's reliability, general English comprehension or real teammate performance. Phase 4 scenarios S06, S07, S09 and S10 remain unintegrated.
