# Role 4 speaking script

Prepared on 3 October 2026 for the planned October 6 presentation. No presentation
or scheduled October 5 peer review has occurred. The script targets two to three
minutes at a comfortable speaking pace, with a short pause between slides. This
is a planning estimate, not a measured human delivery time.

## Slide 1: evaluation framework

My contribution is evaluation, integration, testing and logging. The current build
uses reference backends for all three layers. These are controlled fixtures that
let us inspect behavior before the complete teammate implementations are available.

The framework records the question, beliefs and environment before execution,
public tool calls and returned evidence, belief changes, and the final answer.
It checks whether required tools were used, whether a factual claim matches its
cited evidence, and whether source, confidence and perspective survive the update.
It also checks forbidden movement and whether replaying the trace reproduces the
final belief state. This makes a failure inspectable rather than just assigning a
score to an answer.

## Slide 2: five-case results

The five demonstration scenarios are S01, S02, S03, S07 and S08. Every valid
reference case passes. In each scenario, we deliberately inject a wrong behavior,
and the evaluator detects the intended violation.

For example, S03 keeps the user's red claim, the camera's brown observation and the
historical blue record separate. In S07, memory returns no temperature belief and
the temperature sensor is unavailable. The valid answer says the temperature is
unknown. The injected version invents 22 degrees and requests movement. The
evaluator rejects the unsupported claim, and the dispatcher records movement as
neither authorized nor executed.

There are also 177 available passing test methods: 167 Role 4 tests and ten
teammate client tests. That count is separate from the five scenarios. The five
reference passes establish fixture behavior, while the five deliberate failures
establish evaluator detection. Neither is an LLM success rate. A separate
malformed-temperature probe aborts with a contract error instead of becoming a
valid unknown answer.

## Slide 3: limitations and next milestones

Full test discovery still exits with two collection errors because approved shared
contracts are missing. The sensor stub and a complete agent interface are also
pending. Prem's actual client has been tested through fake APIs only.

Our automated checks validate structured evidence and metadata. They do not
generally understand arbitrary English, so human review of the five exact answers
is still pending. Scenario B also needs agreement on the historical agent identity
and lighting context. The planned October 5 review and October 6 presentation
remain future events. The next work is owner API and fixture agreement, actual
human review, complete integration, and later measured real-model trials.

## Evidence anchors

`../phase_c_verification.json`, `../phase_c_s07_reuse_and_fixture_alignment.md`,
`../phase_c_remaining_integration_gaps.md`, `evidence_summary.json` and the exact
rehearsal artifact paths in `rehearsal_record.json`. The runtime model label is
`deterministic_reference` and scope is `five_case_reference_evaluation`.
