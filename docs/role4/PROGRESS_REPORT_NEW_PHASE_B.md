# New Phase B progress — Yash, Role 4

**Completed for review:** measured offline baseline; exact collection diagnosis;
reference harness verification; conservative available-client compatibility;
historical Phase 4 reuse decisions and updated teammate inputs. Work remains on
feature/yash-evaluation-foundation at base 14fcd6a4804e90f57d42b5dab7d4c40ff7600c8c.

The pre-edit clone baseline was 129 Role 4 + 10 teammate client = 139 available
passing tests, with two collection errors. Phase B adds seven harness and eight
client tests: **144 Role 4 + 10 teammate client = 154 passing available tests**.
Full discovery still has two collection errors; missing official contracts mask
a missing sensor fixture. No partial run is described as a full-suite pass.
All existing Phase 1–3 demos preserve expected results and fault detection.

Harness checks confirm all reference layers reset on reuse, public snapshots
match recorded inputs/final state, calls/evidence pair correctly, malformed and
unavailable reads abort without invented facts, and empty memory produces no
fact evidence. Rejected-action receipts now explicitly say authorized=false,
executed=false; trace_integrity rejects contradictory physical-execution claims.
Existing prose/metadata tests and every human worksheet remain pending review.

New PremClientAdapter calls the unchanged public chat implementation, records
requests/normalised replies/errors, and performs no tool dispatch or run_query
emulation. Four fake-API smoke cases cover text, tool-request parsing, malformed
arguments and propagated timeout. Real procedural client ownership is reported
separately from fake_api execution and partial_pipeline/client_chat_only scope.
The existing ScriptedLLM public path is also exercised as a reference fixture.
No real sensor, memory, full agent or hosted reliability measurement is claimed.

The seven deferred historical files and 40 tests already implement all four
future cases. S07 is suitable for selective Phase C reuse after authorization;
S09 stays Phase E, S06/S10 Phase F. Reuse requires the removed old shared hooks
and authoritative teammate APIs to be reviewed rather than copying everything.
No deferred scenario was migrated or implemented; their entry points still reject.

Original teammate modules/tests/scripts and historical source are preserved.
Phase A reports/evidence/manifest remain historical snapshots. Current Phase B
incremental files are listed in [phase_b_files.txt](phase_b_files.txt); combine
with the Phase A list when later reviewing the entire unpublished contribution.

See [baseline/verification](phase_b_baseline_and_verification.md),
[blockers](phase_b_collection_blockers.md), [compatibility](phase_b_compatibility_matrix.md),
[reuse matrix](historical_phase4_reuse_matrix.md), [inputs](teammate_inputs.md),
and [smoke evidence](phase_b_evidence/README.md).

Recommended Phase C, after authorization: retain S01/S02/S03/S08 reference
regressions, resolve official teammate dependencies, exercise the real single-tool
path offline where possible, selectively adapt historical S07 abstention/status
support, regenerate correctly labelled logs and prepare the mid-project build.
Get actual human prose reviews; neither metadata passes nor fake-API transport
establish semantic approval. Publication and v0.5-flash remain separate approvals.

No commit, push, PR, merge, tag, explicit file deletion, package installation,
environment creation, hosted usage or Phase C implementation occurred. Stop
after Phase B for the user's review.
