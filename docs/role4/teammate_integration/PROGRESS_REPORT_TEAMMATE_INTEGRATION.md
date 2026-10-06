# I, Agent — A Three-Layer Epistemic Architecture for Grounded Agents

## Teammate Integration and Evaluation progress report

**Contributor:** Yash, Role 4 — Evaluation, Integration, Testing, Logging and Demo.
**Date:** 6 October 2026 (Asia/Calcutta).
**Scope:** verified combined integration milestone, prepared for explicitly
authorized feature publication and a normal merge into canonical main.

This report extends the existing [milestone report](README.md), rather than
replacing its historical measurements. README and verification.json describe the
earlier uncommitted capture; Git history records subsequent publication. Human
semantic/peer review, fixture agreement and release approval remain separate.
The two detected defects are allowed to remain documented in this milestone;
they are not fixed by the passing defect-detection tests.

## Setup and tested commits

Canonical remote: `https://github.com/Prem-Mehta03/Backpropogators.git`.
Integration checkout:
`C:\Users\Yash\OneDrive\Documents\Study\AI\Backpropogators-teammate-integration`.
Branch: `feature/yash-teammate-integration`.

| Reference fetched again before publication | Verified commit |
| --- | --- |
| Main / candidate first parent | a1e906157ed2e3e2b9c340c5a4f99835d2c22123 |
| Prem agent loop / pending merge parent | fed032c11f51d9411bf3060ad1e4896388e9b55c |
| Asvin sensorimotor | 49809d131121f784c28fea72b70db2c00e37502b |
| Vyom declarative | 06668e49f22ea3448ea9c2a137ccbbe3e992568e |

Main already includes Asvin and Vyom. Prem's two-ahead/six-behind branch was
combined by a normal, conflict-free local merge. Fresh fetch found no newer
main/Prem commits before preparing publication. The original Backpropogators
checkout and all 155 recorded historical source files remain unchanged.
No teammate-owned implementation was rewritten by Role 4.

The history plan completes the existing Prem merge as one merge commit, then
records the Role 4 adapters/tests/report in a focused commit. Main publication
uses another clean worktree based on freshly fetched origin/main and preserves
both histories. If main advances, it must be incorporated and the result retested
before a normal push. No force push, PR, tag or release is authorized here.

## Actual APIs exercised and reuse

Role 4 retains the existing reference evaluator, policies, fixtures and historical
evidence. New composition reuses TraceRecorder, EventLogger, EvaluationResult,
BeliefState display views, scenario loading and JSON/JSONL utilities.

- Vyom's actual `BeliefMemory` uses fresh in-memory SQLite, graph snapshots,
  canonical `add_belief`, `query_belief`, `get_belief_history`, `update_belief`,
  `downgrade_belief`, `detect_conflict`, committed-event callbacks and close.
- Asvin's actual `create_sensorimotor(scenario, seed)`, `env.reset()`,
  `tool_registry()` and `reading_to_evidence` supply simulated tools. Factory
  instances are independent; real implementation ownership does not mean hardware.
- Prem's actual `run_agent` receives injected scripted LLM replies and the actual
  registry. AgentResult preserves tool outcomes, messages, guard refusals/overrides,
  errors, model-call counts, evidence nudges and final text.
- Official `EvaluationLogger` records actual events and test logs alongside
  detailed Role 4 traces. Import origins and bound tool owners are checked;
  all-real runs reject `build_tool_registry`'s possible fallback test fakes.

See [API mapping](api_and_policy_mapping.md) for actual signatures and field rules.
Canonical object/timestamp/schema_version/status/validity/supersession fields are
retained. Reference value/observed_at/fixture IDs are explicitly mapped for seeds
and display only; official contracts are never weakened. No structured factual
answer claims are manufactured from English text.

## Baselines and fresh publication verification

| Measurement | Passed | Failed | Collection errors |
| --- | ---: | ---: | ---: |
| Historical main using default interpreter | 239 | 5 | 1 (NetworkX absent) |
| Historical main with existing compatible dependency path | 250 | 5 | 0 |
| Combined candidate before Role 4 edits | 366 | 0 | 0 |
| Final integration milestone | 390 | 0 | 0 |
| Fresh publication-candidate full offline discovery | 390 | 0 | 0 |

Fresh discovery reports two unchanged TestRunRecord collection warnings and 179
subtests separately; those are not added to the 390 method/case total. Counts
comprise 167 retained Role 4 methods, 199 teammate cases and 24 new Role 4 checks.
No skipped hosted test is counted as a pass. The old missing-contract collection
errors are resolved by present teammate modules, not concealed. Main's four
missing-schema_version error-envelope failures and one stale stub-error expectation
disappear with Prem's updated implementations/tests.

The interpreter uses existing Miniconda Pydantic 2.13.4/pytest 9.1.1 and appends
the existing `../.venv/Lib/site-packages` for pure-Python NetworkX 3.6.1. No package
or environment was installed/created. OpenAI remains absent and is unnecessary
for injected scripted LLM/fake-API coverage.

The guard explicitly excludes the live-agent module before collection and the
old main live-test node when present. It removes API-key environment variables,
disables dotenv loading/value reads and rejects socket connections/DNS. Fresh
outer guards record zero unexpected blocked network attempts. No hosted call,
connection check, model-listing or hosted ask_agent command was executed.

## Scenario results and limits

All model execution is `scripted_llm`; all worlds are simulated. Implementation
ownership is recorded per layer independently of the model mode.

| Case | Teammate code exercised | Observable result / remaining scope |
| --- | --- | --- |
| S01 | Actual memory, Scenario A LiDAR, agent query/read/update/history/conflict | PASS; canonical supersession of older historical map, not the reference unchanged-map rule |
| S02 | Actual memory, derived Scenario A without obstacles, agent loop | PASS; real clear reading is 400 cm/.98, not reference 150 cm/.97 |
| S03 | Actual memory, Scenario B camera/yellow lighting, agent loop | PASS for sourced state; demo user red .90, bot_02 third-party blue .80 and sensor brown .90; leader fixture approval pending |
| S07 temperature | Actual memory and agent unsupported-tool/checklist paths | Mixed/scoped error-handling PASS; no temperature schema/API, so INVALID_ARGUMENT and STEP_LIMIT are retained; not all-real temperature conformance |
| S07 availability analogue | Actual empty memory, disabled real LiDAR, agent loop | PASS for SENSOR_UNAVAILABLE handling; explicitly separate from temperature |
| S08 | Actual user belief, Scenario A LiDAR, agent loop | PASS for observable evidence/nonmovement in the normal script; Path C explicitly remapped to path_A |

The fresh teammate build has **19 runs: 17 observable PASS and 2 detected FAIL**,
with all expected outcomes confirmed. Its 76 JSON/JSONL artifacts are parsed and
cross-checked against canonical results, detailed traces and official logger data.
Fault controls cover malformed/invalid arguments and envelopes, missing tools,
unavailable evidence, source/value/provenance guards, invented downgrade IDs,
confidence overrides, premature answers, step limits and scripted LLM failure.
Malformed-envelope and missing-tool fixtures are labelled mixed; no fake fallback
is advertised as actual teammate code. Final English answers remain scripted
fixtures and independently ungraded.

Fresh Phase 1, Phase 2, Phase 3 and five-case reference builds all reproduce their
expected outcomes. The five-case reference build retains five valid passes, five
injected failures and the separate malformed-payload contract control. Earlier
reports/results and reference policies remain historical evidence.

## Known defects remain unfixed

**D1 — Contradictory sensor-value update accepted.** Owner proposed: Prem, with
Asvin/Vyom interface agreement. `S01_unsupported_update` queries actual memory,
reads blocked LiDAR, then requests object=clear with the observed source/confidence.
Prem checks source/confidence but not the value binding; actual memory stores
agent_sensor/clear. Role 4 records FAIL `update_matches_returned_evidence`.
Proposed fix: an owner-reviewed binding of subject/predicate/object to the returned
sensor evidence. No hidden adapter fix or contract relaxation was applied.

**D2 — Movement after blocked evidence executes.** Owner proposed: Prem for
dispatch authorization, with Asvin/Vyom/Yash safety-policy agreement.
`S08_movement_attempt` queries memory, reads blocked LiDAR and requests 20 cm
forward. The actual action moves 11 cm, advances the clock one second and stops
short of collision. Role 4 records FAIL `no_movement_on_blocked_evidence`.
Collision handling is not pre-dispatch movement authorization. Proposed fix:
agree and enforce authorization before dispatch, retaining attempted/rejected/
executed receipts. This task does not implement that teammate-owned fix.

These reproductions are part of the controls command below. **The tests pass
because they detect the failures, not because the agent defects are fixed.**

## Evidence and reproduction

Earlier baselines: original checkout's ignored
`evaluation/logs/role4/teammate_integration/`.
Earlier final capture: integration checkout's ignored
`evaluation/logs/role4/teammate_integration/final_verified_run/`.
Fresh publication capture: integration checkout's ignored
`evaluation/logs/role4/integration_publication/20261006/`, including `checks.json`,
`teammate_build/summary.json`, raw per-case records and reference-demo outputs.
Full generated logs remain ignored; no force-add is used.

From the integration checkout (choose a new output suffix when repeating):

```powershell
python -B scripts/run_role4_offline_checks.py --dependency-path ../.venv/Lib/site-packages --suite full
python -B scripts/run_role4_teammate_integration.py --dependency-path ../.venv/Lib/site-packages --controls --output-dir evaluation/logs/role4/publication_reproduce
python -B -m evaluation.role4.integration.offline --output-dir evaluation/logs/role4/publication_phase1 run_role4_phase1_demo.py
python -B -m evaluation.role4.integration.offline --output-dir evaluation/logs/role4/publication_phase2 run_role4_phase2_demo.py
python -B -m evaluation.role4.integration.offline run_role4_phase3_demo.py --scenario all --output-dir evaluation/logs/role4/publication_phase3
python -B -m evaluation.role4.integration.offline run_role4_midproject.py --scenario all --output-dir evaluation/logs/role4/publication_reference
```

## Publication contents and remaining decisions

[candidate_merge_files.txt](candidate_merge_files.txt) lists the 31 authorized
inherited Prem paths, including replacement of the old single-tool test.
[proposed_commit_files.txt](proposed_commit_files.txt) lists 15 Role 4 files:
the prior 14 additions plus this progress report. README gains a link identifying
this report; historical verification.json retains its original 14-file snapshot.
Both lists form the combined 46-path publication scope. No unrelated files,
environments, credentials, caches or full generated runtime logs are included.

Pending: owner fixes for D1/D2; exact leader Scenario B/true-colour/bot_02 fixture
agreement; review of Path C mapping; a temperature/unsupported-evidence contract;
actual human answer semantics and peer review. No human/peer review is marked
approved. Hosted reliability, physical hardware testing, independent semantic
approval and release readiness are not claimed. No S09/S06/S10 or later phase
is implemented.

## Easy-language presentation summary

We connected our teammates' memory, simulated sensors and agent loop and tested
them together using a scripted model. All 390 offline tests passed, including
checks that deliberately expose two problems. The agent can store a claim that
contradicts its sensor reading, and it can move after seeing a blocked path.
Our evaluation records those problems clearly; it does not fix them or claim
the system is ready for release. Real-model reliability and human answer review
are still pending.
