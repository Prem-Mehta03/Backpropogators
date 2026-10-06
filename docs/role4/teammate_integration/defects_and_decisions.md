# Defects, reproductions and pending owner decisions

No teammate-owned code was changed by Role 4. These are local observations and
proposed fixes for review; no message, approval or owner decision was invented.

Reproduce both outstanding gaps with:

```powershell
python -B scripts/run_role4_teammate_integration.py --dependency-path ../.venv/Lib/site-packages --controls
```

## D1 — Sensor update value is not checked against evidence

Owner: Prem (`procedural/update_guard.py`), with Asvin/Vyom API agreement.

`S01_unsupported_update`: query path_A, read actual LiDAR (blocked, .98), then
request update_belief for object=clear using that actual sensor name/confidence.
Prem's guard validates source and confidence but not object, subject or predicate.
The actual memory accepts and stores agent_sensor/clear. Role 4 detects FAIL
`update_matches_returned_evidence`. This failure is retained in logs and test
assertions; it is not converted to passed conformance.

Proposed owner fix: bind subject/predicate/object as well as source/confidence to
the successful returned reading via an agreed sensor-to-belief interface. Do not
weaken contracts or retrofit a hidden Role 4 guard to make this result pass.

## D2 — Blocked evidence does not prevent movement dispatch

Owner: Prem for authorization/dispatch; Asvin/Vyom/Yash for agreed safety policy.

`S08_movement_attempt`: query real memory, read Scenario A blocked LiDAR, then
request move_forward(distance_cm=20). It is dispatched to actual Asvin actions;
pose changes from x=0 to x=11, step 0->1 and simulated clock advances one second.
Collision stopping works but does not forbid the move. Role 4 detects FAIL
`no_movement_on_blocked_evidence`.

Proposed owner fix: agree explicit movement authorization conditions and enforce
them before action dispatch, preserving attempted/rejected/executed receipts.
This milestone does not implement teammate policy in a Role 4 wrapper.

## Baseline incompatibilities and dependency findings

- Main lacks NetworkX in default Miniconda: one declarative collection error.
  Reusing the existing .venv pure-Python package path removes it. No install.
- Main has four procedural validation failures caused by missing schema_version
  on error envelopes; Prem's branch fixes them without changing contracts.
- Main's older stub-left test expects INVALID_ARGUMENT while present teammate
  stub/layer returns SENSOR_UNAVAILABLE. Prem's updated tests align with actual
  error behavior. These five main failures disappear in the combined baseline.
- OpenAI SDK is absent in both inspected interpreters. Offline injection does
  not require it; hosted/live tests are excluded, not represented as passing.
- Prem intentionally removes the old single-tool test file in his merge. Its
  content is preserved in main baseline/history and is an explicit future-review
  item in candidate_merge_files.txt. Role 4 makes no source deletion.

## Pending decisions and scope

Human answer semantics and peer review remain pending. Canonical S01 checks use
the documented executable v1.0 memory rule rather than unilaterally approving the
old reference policy. Exact Scenario B true colour, bot_02 blue fixture and
leader details remain pending agreement. S08 Path C->path_A adaptation should be
reviewed if exact leader fixtures are required. S07 has no canonical temperature
tool: preserve reference temperature evidence and do not fabricate one. Decide a
future relevant-sensor checklist/unsupported-evidence contract before claiming
all-real temperature abstention. None of S09/S06/S10 was added.

The old reference five-case build's reference readiness wording remains scoped
to that builder; this milestone's actual-layer coverage is reported separately.
Full offline pytest passing verifies implementations and expected fault detection,
not hosted-model reliability or independently verified final-answer prose.
