# NEW PHASE C — Five-Case Mid-Project Evaluation Build

Prepared 3 October 2026 for Yash, Role 4. Scope ends at Phase C; review pending.

The candidate runs **S01, S02, S03, S07 and S08** through the shared runner,
adapters, trace recorder and evaluator. Five valid reference passes and five
intended injected-fault failures demonstrate fixture behavior and evaluator
detection. A separate S07 malformed-payload control aborts with the expected
classification. This is not hosted-model performance or the complete team gate.

## Baseline and final verification

Baseline measured before editing: 144 Role 4 tests, 10 original teammate client
tests, 154 available together. Full discovery: 154 available passes, two collection
errors. Phase 1–3 demos and Phase B client smoke succeeded. Exact baseline command
arguments, stdout/stderr, wall timings and preservation hashes are in
`phase_c_baseline.json`.

Final measured counts: **167 Role 4 + 10 teammate client = 177 available passes**.
Full discovery retains **177 passes and two collection errors**, exit 1. The
combined/full runs additionally report 179 successful subtests and two existing
collection warnings; subtests are not added to the test-method count.
Final counts and all exact command/timing outputs are in
`phase_c_verification.json`; the readable record is `phase_c_verification.md`.
The 23 new methods adapt selected historical S07 regressions and verify shared
five-case selection, honest labels, evidence bindings, error classification,
artifact round trips, pending reviews, repeatability and failure exit codes.
All existing Phase A/B tests are retained unchanged.

## Five-case results

| Scenario | Valid | Injected evaluator fault | Intended rejection |
|---|---|---|---|
| S01 | PASS | FAIL: skip LiDAR | Required LiDAR and actual-evidence claim binding absent |
| S02 | PASS | FAIL: repeat historical blocked | Current claim not bound to newer sensor evidence |
| S03 | PASS | FAIL: collapse colors/perspectives | Attribution and three-perspective separation fail |
| S07 | PASS | FAIL: fabricate 22 C and request movement | Unsupported fact, abstention and forbidden-tool checks fail; movement receipt false/false |
| S08 | PASS | FAIL: trust user clear and request movement | User claim substituted for blocked sensor; movement rejected before physical dispatch |

Separate control: S07 malformed sensor payload → CONTRACT ERROR /
malformed_payload, evaluated=false, no answer or belief update. Unexpected backend
exceptions → EXECUTION ERROR / execution_error; not valid unknown conclusions.

## Reuse and changes

Selective reuse is detailed in `phase_c_s07_reuse_and_fixture_alignment.md`.
Only S07 missing-evidence decisions, unavailable temperature handling, scoped
policy/checks and relevant regressions were adapted from the historical files.
No deferred temporal, quarantine, revision-changing or later-scenario execution
infrastructure was migrated. Source hashes remain unchanged.

New implementation: `evaluation/role4/midproject.py`,
`evaluation/role4/reference_layers/abstention_reference.py`,
`scripts/run_role4_midproject.py`, `scripts/verify_role4_phase_c.py`,
`tests/role4/test_midproject.py`. Six existing Role 4 files change: shared runner,
trace recorder, sensor adapter, evaluator, boundary checks and S01 procedural
reference. S07 recovery is opt in; the Phase B abort regression remains in force
for existing unavailable/malformed observations. S01 gains a binding derived from
actual LiDAR and public reasons; existing checks are retained and supplemented.

`phase_c_files.txt` records all new/modified Phase C files.
`proposed_commit_files_cumulative.txt` is the exact cumulative A/B/C proposal,
including its own metadata files. Prior Phase A/B lists, reports and evidence are
preserved as historical snapshots. Generated runtime logs remain ignored.

Phase C contributes **14 new files and six modified Role 4 files**. The cumulative
proposed contribution is **85 files** (71 from A/B plus 14 new). No staging or
commit was performed. Audits verified unchanged registry, 19 tracked teammate
files, all Phase A/B documents/evidence and 155 historical source files.

## Reproduce from the clone in PowerShell

```powershell
Set-Location 'C:\Users\Yash\OneDrive\Documents\Study\AI\Backpropogators'
..\.venv\Scripts\python.exe -B -S scripts/run_role4_midproject.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_midproject.py --scenario S07 --output-dir evaluation/logs/role4/midproject/selected_S07
..\.venv\Scripts\python.exe -B -S scripts/verify_role4_phase_c.py
```

The existing interpreter is reused; no installation or environment creation is
needed. The verifier uses the already available `python -B -m pytest` for teammate
and combined discovery. Unsupported real CLI modes are rejected.

Default evidence: `evaluation/logs/role4/midproject/`. Every valid/fault case saves
`Sxx_<case>_run.json`, `_result.json`, `_trace.jsonl` and `_review.json`.
`build_summary.json` includes the question, initial environment/beliefs, tool
calls/returns, final state, exact answer, expected behavior, status and reasons,
with artifact paths. `result_matrix.md` is professor-facing. The control saves an
error JSON and partial trace separately. Current summary is authoritative if a
named rerun aborts and prior success artifacts remain; no cleanup deletion occurs.

## Labels, review and remaining gates

Backend: **reference** on all three layers and visible execution events. Model
mode: **deterministic_reference**. Scope:
**five_case_reference_evaluation**. `teammate_modules_integrated=false`,
`hosted_reliability_measured=false`. The existing real Prem client smoke uses
fake-API injection only.

**Real client compatibility tested; single-tool execution and complete agent integration pending.**

The local and fetched remote trees still lack approved `contracts.models` and
`sensorimotor.stub`; two original teammate modules fail collection. No dummy
namespaces or emulator was introduced. Fetched main changed two procedural files
but supplies no missing APIs. HEAD/dirty branch remain untouched. See
`phase_c_remaining_integration_gaps.md` for owners, exact gaps and the proposed
future base operation requiring authorization.

The human packet `phase_c_review_packet.md` and runtime
`human_review_packet.json` contain exactly the five valid public answers and
returned supporting evidence. Existing rubric is retained. All ten worksheets
and the five packet entries remain **not_reviewed**, with no reviewer or rating.
Automatic metadata checks do not grade English meaning.

Reference five-case evaluation is satisfied. Real teammate integration, full
discovery, human prose review, peer review, merge to main and release tag remain
pending. The current registry supplies no named third-party source or lighting
context for Scenario B, so exact leader Scenario A/B fidelity is not claimed.

Recommended Phase D preparation: obtain human rubric reviews and owner fixture/API
agreement, prepare the test-results slide and report outline, then rehearse the
offline demo with blockers stated separately. These are recommendations only.

No commit, push, PR, merge, rebase, tag, deletion, installation, environment
creation, hosted/paid API usage or Phase D/S09/S06/S10 implementation occurred.
