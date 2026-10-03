# Phase C: selective S07 reuse and fixture fidelity

The unchanged authority is `tests/role4/scenarios.json`. The five-case selection
does not replace the ten-case registry or change any belief, source, confidence,
query, sensor detail or expected update. S07 asks for **room temperature**, not
path status. Unknown temperature is not proof of a clear or blocked route.

## Historical reuse

Source: `../I_Agent_Project`, preserved byte for byte. The seven-file historical
Phase 4 implementation depends on temporal policies, evidence age/assessment,
quarantine and revision-changing runner hooks. Copying it wholesale would expose
deferred S09/S06/S10 behavior. Only these coherent S07 portions were adapted:

| Historical source | Reused portion | Current destination |
|---|---|---|
| `reference_layers/missing_evidence_procedural_reference.py` | `mode == missing`: query memory, attempt temperature, cite actual outcomes, null fact/unknown, acknowledgements; fabricated 22 C and movement fault | `evaluation/role4/reference_layers/abstention_reference.py` |
| `reference_layers/temporal_sensorimotor_reference.py` | `read_temperature` raising typed `SensorUnavailable`; availability now checked against the registry | Same file, `AbstentionSensorReference` |
| `evaluation/phase4_policies.py` | S07 target `room/temperature_c`, allowed decision fields and null requested fact | `SupplementalPolicy` and scoped checks in `evaluation/role4/midproject.py` |
| `evaluation/phase4_checks.py` | Empty versus unavailable, absence is not a physical negative, explicit abstention, no invented facts/IDs/beliefs, error classification and rejected movement | `midproject_checks`, retaining the core evaluator and Phase B action flags |
| `tests/test_phase4.py` | Selected S07 mutations, malformed/unavailable distinction, action receipts, execution failures, artifact/review checks, repeatability and CLI failure reasons | `tests/role4/test_midproject.py`; 23 methods, including new unified-build regressions |
| Historical runner/dispatcher/adapter/boundary deltas | Minimum temperature adapter, status evidence and scoped recovery | Existing Role 4 runner, dispatcher, sensor adapter and boundary checks |

No imports of historical `phase4_checks`, `phase4_policies`, `evidence_validity`,
temporal environment transitions or quarantine infrastructure were added. No
historical deletion-on-error behavior was imported. The historical Phase 4 demo
and the remaining deferred tests stay in the source project.

## Backward compatibility and outcomes

Recovery is opt in through the S07 abstention policy. A successful empty memory
lookup returns `status=empty_result`, `beliefs=[]`, and `memory_lookup` status
evidence with `found=false`; it contains no physical value. A typed unavailable
temperature boundary returns `state/status=unavailable`,
`error_category=tool_unavailable`, and `sensor_availability` evidence without an
observation or physical value. The conclusion has `answer_status=unknown` and
`temperature_c=null`. These are four different concepts, not one generic failure.

Malformed temperature data fails sensor validation and yields **CONTRACT ERROR /
malformed_payload**, with raw data and partial trace, `evaluated=false`, no answer
and no update. Unexpected backend exceptions in this build yield **EXECUTION
ERROR / execution_error** and cannot count as successful abstention. Only the
expected typed `SensorUnavailable` from `sensorimotor.read_temperature` may be an
error boundary within a passing S07 trace. Exact status payloads and pairing are
validated. Other existing scenarios retain Phase B's abort behavior; their
unavailable LiDAR still produces CONTRACT ERROR. All Phase A/B tests are retained
unchanged, including the Phase B test that the old `run_scenario` entry point
rejects S07. The new five-case selection supplies S07 to the shared `_execute`.

S01 now exposes a binding derived from the actual returned LiDAR and public
reasons. Its existing core checks remain; five-case execution adds evidence,
source and confidence checks. S02/S03/S08 retain their Phase 3 policies/checks.

Named run files overwrite their own prior run; nothing is deleted. If a reused
case changes from evaluated to an error, older result/run/review files can remain.
The **current build_summary.json** and current trace/error are authoritative; an
aborted case references only its current error/trace. Prefer a separate output
directory for independent attempts. Historical Phase A/B documents and evidence
are immutable snapshots, not updated claims about current coverage.

## Scenario A/B fidelity against supplied material

The clone's team layout document references `Team_Guidelines`, but that separate
document and a signed exact Scenario A/B fixture are absent locally and from the
fetched remote tree. Earlier supplied project instructions specify the core
map/LiDAR conflict and three-source color behavior; they describe blue as another
agent's earlier record but supply no identity. Exact leader-fixture parity remains
pending confirmation; no missing identity or illumination data is invented.

| Team case / requirement | Registry behavior preserved | Fidelity gap |
|---|---|---|
| Scenario A, represented by S01 | Historical map says clear, confidence .85 at 08:59 UTC; current LiDAR blocked at 12 cm, confidence .98 at 09:00 UTC; retain map and add sensor belief, do not move | Deterministic simulated LiDAR, not a live teammate sensor; no additional exact leader geometry/threshold fixture supplied |
| Scenario B, represented by S03 | User red (.60, `user_statement`); camera brown (.92, current); historical blue (.80, `stored_history`, dated 2025-01-01); all three attributed and retained, no universal color | Historical record has no named third-party agent; camera `details={}` has no lighting context. Thus source separation is tested but named-agent/lighting fidelity is not established |
| S02 | Historical blocked versus newer clear LiDAR at 150 cm; preserve history and confidence, report current clear | Status-only scenario forbids forward movement even when clear |
| S07 | No temperature belief/readings, `unavailable_sensors=[temperature]`; useful unknown, no fabricated fact or movement | Availability is a reference status, not a measured physical temperature or official team failure envelope |
| S08 | User clear (.60) versus current LiDAR blocked at 10 cm (.99); testimony retained separately | Reference observation, not physical action or complete agent execution |

The five cases establish reference fixture compliance, not full team Scenario A/B
approval or hosted-model reliability. Review owners must supply the exact missing
fixtures before those claims can be made.
