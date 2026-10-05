# Phase C integration and release gaps

**Real client compatibility tested; single-tool execution and complete agent integration pending.**

Prem's actual `LLMClient.chat` is exercised offline with fake-API injection. Its
ten available original client tests and Role 4 client adapter smoke run. No hosted
model, complete agent loop, production memory/sensor chain or reliability trial
was executed. Five-case traces label every layer `reference`, model mode
`deterministic_reference`, integration scope `five_case_reference_evaluation`.

## Missing inputs and full discovery

| Owner / input | Current blocker and required next evidence |
|---|---|
| Vyom: approved `contracts.models` | Missing namespace; `test_tools.py:7` imports it directly, while `test_single_tool_call` reaches it through `procedural/tools.py:14`. Both fail collection. Need the owner's actual models and error-envelope contract. |
| Asvin: compatible `sensorimotor.stub` or approved replacement API | Missing namespace; original teammate tests require `from sensorimotor import stub`. Hidden behind the earlier contracts error. Need approved offline sensors/tool registry and failure semantics. |
| Vyom/Asvin production APIs | Need public reset, snapshots, beliefs/history/upserts, immutable provenance/confidence, sensor environment/revision and observation schemas. Current Role 4 contracts are scoped evaluation references, not official replacements. |
| Prem complete agent API | Published single-tool proof lacks a complete stateful `run_query`, reset, claim-support metadata and bounded agent lifecycle. Need actual public entry point and outputs before adapting. |
| Team logging owner | Existing Role 4 JSON/JSONL format used; no newly approved canonical team log schema supplied. Agree mapping without overwriting another owner's logger. |
| Leader's exact Scenario A/B fixtures | Need named historical agent, lighting context if required, exact geometry/thresholds and approval of registry mapping; see fixture alignment document. |

Full discovery retains two collection errors. Twelve offline functions (seven
tools and five single-tool) remain uncollected. The one live function is excluded
by `-k "not live"`; its module fails collection first, so this is not a measured
pytest skip. The full-suite exit code remains 1 even when all available tests pass.
No dummy `contracts.models` or `sensorimotor.stub` was created.

## Fetched remote and safe proposed base operation

Current branch `feature/yash-evaluation-foundation` and HEAD
`14fcd6a4804e90f57d42b5dab7d4c40ff7600c8c` stay unchanged. Authorized fetch advanced
`origin/main` to `d350805b350e261fd874f72c5be097a920dd614e`. Inspection found only
comment changes in `procedural/llm_client.py` and `error_result` validation via
`ToolResult.model_validate(...).model_dump()` in `procedural/tools.py`; neither
missing official module was published. The dirty branch was not merged or rebased.

For a later approved integration: preserve and review the scoped Role 4 candidate,
then, only with authorization to record that work and change the base, merge the
verified `origin/main` into the feature branch (or choose the team's agreed rebase
workflow), inspect conflicts, and rerun owner tests. No base-changing operation is
needed to complete this reference build, and none was performed in Phase C.

## Candidate readiness for later v0.5-flash review

| Condition | Status |
|---|---|
| Five-case reference evaluation with valid/fault logs | Satisfied by structured validation |
| Real teammate three-layer integration | Pending |
| Full test discovery | Blocked: two original teammate collection errors |
| Human prose review | Pending: all worksheets `not_reviewed` |
| Peer review | Pending |
| Merge to main | Pending; no publication authorized |
| Release tag | Pending; no tag created |

The complete team gate has not passed. Phase D recommendations only: review the
five exact answers against the existing rubric, obtain fixture/API owner input,
prepare a results slide and report outline with reference versus real coverage
shown separately, and rehearse the offline command. No Phase D artifact or later
scenario implementation was produced here.
