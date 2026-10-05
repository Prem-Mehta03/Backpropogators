# Role 4 slide content and speaker notes

Three editable slides. Prepared 3 October 2026. Human and peer reviews pending.

## Slide 1: Evaluation framework and audit trail

**Visible scope: Reference-backed evaluation**

- Required tools and forbidden actions / Question and initial state
- Claims bound to returned evidence / Public calls and raw tool returns
- Source, confidence and perspective / Evidence IDs and before/after beliefs
- Belief changes and trace replay / Answer, check results and reasons
- Human prose review remains pending. Automated checks validate structured metadata.

**Speaker notes:**

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

Evidence: evaluation/role4/evaluator.py; evaluation/role4/integration/trace_recorder.py; docs/role4/phase_c_verification.json

## Slide 2: Five-case results and deliberate faults

**Visible scope: Reference-backed evaluation**

- S01 / PASS / FAIL (expected) / Missing LiDAR
- S02 / PASS / FAIL (expected) / Historical claim used as current
- S03 / PASS / FAIL (expected) / Perspectives collapsed
- S07 / PASS / FAIL (expected) / Fabricated temperature, movement request
- S08 / PASS / FAIL (expected) / User claim replaces blocked sensor
- 177 available test methods = 167 Role 4 + 10 teammate client
- Separate malformed S07 control: CONTRACT ERROR / malformed_payload
- No LLM reliability measurement

**Speaker notes:**

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

Evidence: docs/role4/phase_d/evidence_summary.json; docs/role4/phase_d/rehearsal_record.json; tests/role4/scenarios.json

## Slide 3: Integration blockers and next milestones

**Visible scope: Reference-backed evaluation**

- contracts.models and sensorimotor.stub missing
- Full discovery: 2 collection errors, exit 1
- Complete agent and hosted trials pending
- Scenario B identity and lighting unspecified
- October 5: peer review planned
- October 6: presentation planned
- Agree owner APIs and exact fixtures
- Human review, integration, then release gates
- Prem's real client used fake APIs only. Human and peer reviews remain pending.

**Speaker notes:**

Full test discovery still exits with two collection errors because approved shared
contracts are missing. The sensor stub and a complete agent interface are also
pending. Prem's actual client has been tested through fake APIs only.

Our automated checks validate structured evidence and metadata. They do not
generally understand arbitrary English, so human review of the five exact answers
is still pending. Scenario B also needs agreement on the historical agent identity
and lighting context. The planned October 5 review and October 6 presentation
remain future events. The next work is owner API and fixture agreement, actual
human review, complete integration, and later measured real-model trials.

Evidence: docs/role4/phase_c_remaining_integration_gaps.md; phase_c_s07_reuse_and_fixture_alignment.md; phase_d/teammate_decisions_unsent.md
