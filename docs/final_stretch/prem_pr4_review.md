# Role 4 Review of Prem PR 4

Prem's [initial PR #3 review](https://github.com/Prem-Mehta03/Backpropogators/pull/3)
and [follow-up](https://github.com/Prem-Mehta03/Backpropogators/pull/3#issuecomment-7104507053)
identify the standalone PR combination, scoped S07 reporting, and the remaining
S09 abstention as separate issues. The 23 November v1.1 candidate already contains
both PR heads and retains the movement checks as regressions.

Reviewed [PR 4](https://github.com/Prem-Mehta03/Backpropogators/pull/4) at
`e11d065b6a16e849f13cda204c25d34a99d19ee3`. The request to Yash covers
the two Role 4 files changed by Prem and using `FrameRecorder` in the
acceptance runner.

The unchanged PR head passed 191 Role 4 tests and 179 subtests with no
blocked network attempts. The combined candidate also exercises the
new v1.1 contracts and exact T01–T10 scenarios.

- The old S08 expectation of 11 cm actual movement is historical. In the
  candidate, the requested motion is rejected before dispatch, the
  automatic 12 cm LiDAR receipt is preserved, the move returns
  `CONFLICT`, and the pose stays at x=0.
- Dispatch evidence is matched on request ID and tool. An automatic read
  can share the model's move ID, but cannot be counted as dispatched
  movement. The runner compares automatic boundary receipts against the
  move guard's recheck receipts.
- `evaluation/runner.py` captures frame zero and passes
  `FrameRecorder.on_step` through an observer that also preserves the raw
  tool envelope and automatic flag. The T08 and T10 traces show the
  automatic read before the refused move. A scenario can have multiple
  automatic reads when multiple distance sensors are enabled.
- The candidate extends the guards to reject a contradictory value or
  subject even when the model cites a genuine sensor source. It also
  requires and logs the enabled ultrasonic check. These fixes are kept
  in the candidate for review by the procedural owner.

## Scoring and historical findings

| Finding | Review disposition |
| --- | --- |
| D1 contradictory update, D2 blocked movement, and S10 stale movement | Keep the three original requests as regression controls. They exercise refusal of a contradictory write or cancellation of a move, including the raw receipt and unchanged state. |
| S07 unsupported temperature | Keep the diagnostic verdict visible in its raw records. Exclude it from the behavior pass numerator. The v1.1 T07 acceptance case is a different fixture, an unknown camera target. |
| S09 battery abstention | The configured battery case now accepts an explicit abstention after an unsourced memory lookup and a rejected request for the unavailable matching sensor. It records that the level cannot be verified and leaves memory and pose unchanged. T09 uses valid LiDAR evidence to qualify an unsourced map claim. |
| Exact Scenario A and B | Canonical S01 and S03 now share the v1.1 acceptance seeds. S01 starts from `default_map` 1.00 and checks the query, read, downgrade and update order. S03 verifies all three attributed beliefs remain active and the conflict list is empty. The pinned T01 and T03 traces supply the release report's fixtures. See [fixture details](README.md#fixture-choices). |

## Follow-up verification

The updated checkout passed 593 offline tests and 179 subtests with two
existing warnings and zero blocked network attempts. The five-trial legacy
regression run gave these results:

| Scope | Result |
| --- | --- |
| Canonical and mixed behavior | 45/50 planned, 45/45 exercised |
| Scoped S07 diagnostics | 5/5 met probe criteria. Excluded from behavior passes. |
| S09 evidence-bounded abstention | 5/5 within the behavior result. The scripted model asks to abstain and the agent generates the answer. |
| Canonical regression controls | 15/15 |
| Reference behavior | 50/50 |
| Reference fault detection | All 10 detected |
| Contract boundary samples | 14 across 11 tools passed |

The raw canonical verdict count is 50/50 because it includes the five
scoped diagnostics. The strict run exits 2 for those five outstanding
scope entries. Use the [runbook](../role4/final/demo_runbook.md) to
reproduce the run. The refreshed T01–T10 suite passed all 30 scripted trials
with no fallbacks. See the [measured verification](prem_review_verification.json)
and the [previous full trace capture](README.md).

## Proposed merge order and owner checks

The local checkout combining only the original PR #3 and #4 heads reproduced
both reported failures and the S10 artifact verification error. The earlier S10
expectation assumed the stale request would move 11 cm. This branch already
contains both heads and the updated regression checks. Prem's proposal is to
review and merge PR #4 first, review the
final stretch next, then mark PR #3 superseded once its changes are present.
Confirm the order with the owners, and rerun the combined candidate against
the current base before merging.

Compare the extra changes on `feature/yash-final-stretch` with the PR #4
head. The path filters let owners review their own interfaces and tests.

```sh
git diff origin/feature/prem-agent-loop..origin/feature/yash-final-stretch -- procedural/ scripts/tool_wiring.py scripts/frame_recorder.py tests/procedural/
git diff origin/feature/prem-agent-loop..origin/feature/yash-final-stretch -- contracts/ declarative/ evaluation/logger.py
git diff origin/feature/prem-agent-loop..origin/feature/yash-final-stretch -- sensorimotor/ adapters/ ui/live/ scripts/live_ui.py
```

Prem's procedural review, Vyom's contracts and memory review, and Asvin's
sensor and replay review remain pending. The technical findings here are
Role 4's checks. See the [team review packet](../role4/final/review_packet.md)
for tracked approval and release decisions.
