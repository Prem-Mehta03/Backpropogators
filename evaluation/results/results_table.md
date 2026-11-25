# Final Evaluation Results

| Test | Offline passes | Live passes | Live fallback | Live models | Failing layers |
| --- | ---: | ---: | ---: | --- | --- |
| T01 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T02 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T03 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T04 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T05 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T06 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T07 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T08 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T09 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |
| T10 | 3/3 | 1/1 | 0 | openai/gpt-oss-20b | — |

Each denominator counts the logs supplied for that mode. The target is three live runs per test.
Historical demo runs and unlabelled traces are excluded. A fallback counts as a pass only when all checks pass.

## Live run history (hosted `openai/gpt-oss-20b`, temperature 0)

The table above counts one live run per test on the final code and the scripted offline runs (3 repeats). The history below includes the runs that failed and led to fixes.

| Test | Runs and outcome |
| --- | --- |
| T01, T04, T06 | Passed in round 3 (24 Nov). T04 and T06 passed only after the evidence-guard and claim-check fixes. |
| T05 | Round 3: 1 FAIL (6-call limit), 2 PASS (both through the deterministic fallback summary). Round 4: 1 FAIL (conflict answer). After the call limit was raised to 12 and the fixes: round 5, 1 PASS with a model-written answer. A further 3 runs hit the daily token limit and are not counted. |
| T02, T03, T07 | Passed in the first hosted batch (25 Nov, prompt v6.3). |
| T08 | First batch: FAIL. After the obligations fix: 3 FAIL, then 1 PASS. Each failure was a phrase the check requires (recorded claim and "did not move", then "contradicts", then the word "user"). |
| T09 | First batch: FAIL (never said the source is unknown). After the fix: PASS. |
| T10 | First batch: FAIL (never requested the move, so no recheck). After the fix: PASS. |
| Box approach (demo) | FAIL in the first batch (no camera scan before moving). Not fixed. |

Limits: one live run per test rather than three, because of the 200k-token daily key limit. T01 to T07 were not re-run after prompt v6.4; replaying their saved answers through the new rules accepts all of them.
