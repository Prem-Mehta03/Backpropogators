# Keywords and likely professor questions

## Pocket keyword sheet

Slide 1: public boundaries; before/after state; evidence IDs; source and confidence;
perspective; forbidden tools; trace replay.

Slide 2: five scenarios; five valid passes; five intended fault failures;
S03 red/user, brown/camera, blue/history; S07 empty/unavailable/unknown;
movement authorized=false, executed=false; 177 methods = 167 + 10.

Slide 3: reference-backed evaluation; two collection errors; real client/fake API;
human prose review pending; exact fixtures pending; October 5/6 planned.

## Questions and defensible answers

| Question | Answer | Evidence |
|---|---|---|
| Is this dummy data? | The demonstration uses deterministic reference fixtures. They make calls, state changes and known fault expectations reproducible. They establish behavior for those fixtures. Production or hosted performance is still unmeasured. | `evidence_summary.json`; registry `tests/role4/scenarios.json` |
| Is the real three-layer agent integrated? | No. All five-case layers are references. Prem's actual `LLMClient.chat` was tested with fake-API injection, at client scope only. Single-tool execution and complete integration are pending. | Phase C integration gaps; Phase B client smoke evidence |
| What do the 177 passes mean? | Phase C measured 167 Role 4 methods plus ten original teammate client methods. The 179 pytest subtests are reported separately and do not increase 177. Five scenarios are a different unit. Full discovery also has two errors, so the full suite did not pass. | `../phase_c_verification.json`, combined/full command outputs |
| How does a claim retain provenance? | Returned evidence has an ID and source. Claim bindings retain its value, perspective and confidence. Recorded updates must match the cited returned observation's value, source, confidence and timestamp. Original records remain inspectable. | `evaluation/role4/evaluator.py`; `behavioral.py`; S03 returned evidence and `claim_support` |
| Which perspective is the box's true color? | This fixture reports red as user testimony, brown as current camera observation and blue as history. The evaluator requires separate attributions and rejects a universal color claim. The registry gives no historical agent identity or lighting explanation, so we cannot infer them. | S03 registry; `perspective_separation` and `no_universal_color` checks; fixture alignment |
| Is the source confidence a calibrated probability? | The evaluator preserves the supplied numeric confidence. This work has not established statistical calibration. | Returned fixture confidence and `confidence_preserved` check |
| Why does an unknown answer pass? | S07 explicitly has no temperature belief and an unavailable temperature sensor. A null temperature and missing/uncertainty acknowledgements fit that evidence. An empty lookup does not establish a negative physical fact, and unavailable status does not establish a temperature. | S07 valid `claims`, `query_memory` and `read_temperature` tool results |
| Does every sensor failure become unknown? | No. Only expected typed temperature unavailability in S07 can recover. Malformed payloads abort as CONTRACT ERROR / malformed_payload. Unexpected exceptions are execution errors. Existing Phase B cases retain abort behavior. | S07 malformed control; shared runner/dispatcher; Phase B regressions |
| Did the robot move during the fault? | No. The dispatcher rejected the request before invoking a movement backend. The returned receipt states `state=rejected`, `authorized=false`, `executed=false`. The trace has no movement boundary call. | S07 fault `call_003` or S08 fault `call_004`; Phase C movement regression |
| Why show a bad answer? | The deliberately injected behavior tests the evaluator. A failing fault case is expected when its named checks detect the intended defect. It is not a sampled agent failure rate. | Build summary `fault_demonstration`, `required_failure_checks`, `expectation_met` |
| Does the evaluator understand English? | It checks structured claims and observable trace evidence. Arbitrary prose meaning needs human review. Existing tests document that prose can contradict passing metadata. Every human worksheet remains pending. | `response_review.py`; existing prose/metadata regression; five-response review packet |
| Can we claim 100% LLM reliability? | No. These are five specified reference cases, not a distribution of hosted model trials. Future reliability work needs measured real-model runs, a defined trial set and error accounting. | Build labels `hosted_reliability_measured=false`; Phase C gap report |
| Why does discovery fail despite passing tests? | Two original teammate modules cannot import approved `contracts.models`. `sensorimotor.stub` is also absent and masked by that earlier failure. Available passing tests do not remove these import errors. | Phase C full-discovery stdout, exit 1 |
| What is ready for release? | The Role 4 contribution is prepared for review and possible later publication. Real integration, full discovery, human/peer review, main merge and the v0.5-flash tag remain pending. | Publication plan and release checklist |

These answers describe inspected artifacts, not a new Phase D test-suite execution.
No reviewer decisions or future model measurements are assumed.
