# I, Agent flash talk: speaker notes and Q&A prep

Talk: Tuesday 6 October 2026, 4:00 PM, D-LT10. 4 slides, 3 to 4 minutes, one or two presenters. 10% of the grade. The contributions slide is required.

The brief says "3-slide PPT". Our deck has a cover slide plus three content slides. If you want to stay strictly at three, drop slide 1 and keep its team name and problem line at the top of slide 2.

Target length is about **3 minutes 20 seconds**, which leaves a buffer inside the 4-minute limit. Practise it once aloud with a timer. The full word-for-word script is in section 6 of the deck source file.

## 1. Who says what (two presenters)

| Slide | Content | Time | Presenter |
| --- | --- | --- | --- |
| 1 | Team name, problem, goal | 0:25 | Presenter A (Prem) |
| 2 | Three-layer architecture | 0:55 | Presenter A (Prem) |
| 3 | Milestones and live evidence | 1:25 | Presenter A (Prem) |
| 4 | Contributions and next steps | 0:40 | Presenter B (a teammate who can speak for the other three layers) |

If you present alone, say each person's contribution in one clause on slide 4. Do not skip any member.

## 2. Slide 1: cover and problem (about 0:25)

1. "We are Team BackPropogators, and our project is I, Agent."
2. The problem in two sentences: agents act on beliefs they can't verify, and they mix up whose belief is whose.
3. The goal: check evidence before answering, notice disagreement, update beliefs, explain the source.

Transition: "Here is how we built it."

## 3. Slide 2: architecture (about 0:55)

Point at the three layer cards, then the contract bar between them.
- Declarative (Vyom): beliefs with source, confidence, time, perspective.
- Procedural (Prem): the LLM loop that picks tools.
- Sensorimotor (Asvin): a simulated robot with LiDAR, camera, movement.
- Say the three design rules: one validated contract, rules in code not prompts, check before answering.

Transition: "So does it work? Here is our test case."

## 4. Slide 3: milestones and live evidence (about 1:25)

1. Milestones first (10 s): "Weeks one to five are complete."
2. The test (15 s): the map says clear, the LiDAR sees 12 cm.
3. Point at the diagram left to right (35 s): the map belief at 1.0, the lowered successor at 0.2, the LiDAR belief at 0.98, active. Say: "Nothing is deleted. Each change adds a new belief that supersedes the old one."
4. The four result cards (15 s): 3 of 3 runs, unknown object, enforced in code, 120+ tests.
5. The status line (10 s): this last run used all three real layers; the other scenarios and the full test run are next.

Transition: "That's the work. Here is who did it."

## 5. Slide 4: contributions and next steps (about 0:40)

One concrete thing per person, then the commit counts, then what is next.
- **Vyom:** the belief and provenance schema, the contracts package, the graph and SQLite storage, and the conflict and priority rules.
- **Asvin:** the simulated world, LiDAR, camera, position and movement tools, the lighting model, and the sensor-to-belief adapter.
- **Prem:** the LLM client, the 11 tool wrappers, the reasoning loop, the prompt and evidence policy, and the checks enforced in code, plus 120+ tests.
- **Yash:** the repository and test setup, the 10 test cases, the evaluation harness, and integration.
- **Commits (6 Oct, all branches):** Vyom 4, Asvin 6, Prem 6, Yash 5. Say: "Commit counts are a rough indicator. We work in small reviewed pull requests, and several people's work lands through one person's commit."
- **Next:** instructor feedback, the remaining tests, then the verification report and final demo on 15 November.

Finish: "Thank you. We're happy to take questions."

## 6. What the other team showed (NeuralNexus demo video)

Sir will compare groups, so know what a neighbouring project looks like. This is from a silent 60-second screen recording, so it shows what was on screen, not what they said or what is behind it.

**What their demo shows:**
- A web app called "GroundTruth | I, Agent" on localhost, with a chat box ("Run cycle"), two preset buttons (Scenario A and Scenario B) and a reset button.
- A side panel with the same three layers: Declarative, Procedural, Sensorimotor.
- A "System inspector" panel with tiers: reasoning and outcome (plan, proposed tool, arguments, executed operations and evidence, belief revisions, audit events), graph and evidence ledger, physical environment, perspectives, and raw sensor telemetry with confidence.
- A 3D belief graph page (NetworkX data, 17 active nodes and 23 active facts) with a toggle between active beliefs and belief history, search, a legend (active, superseded, new or revised), and a node inspector showing connected beliefs with source and confidence.
- Scenario A: "Is the front route clear to move forward?" The answer says the static map says clear, but live LiDAR sees an obstruction at 12.0 cm, so it downgraded map confidence and updated the belief graph. A badge reads "grounded conflict resolved".
- Scenario B: three perspective cards for a red box: user expectation (red), live camera view (brown, under yellow lighting), historical record (blue, from bot_02).
- The same model we use (`openai/gpt-oss-20b`), and a robot-pose query.

**What this means for us:**
- Their main advantage is **visibility**. A grader can see the belief graph and the audit trail. Ours is a terminal and JSON logs.
- The scenarios and numbers match ours (12 cm LiDAR, brown under yellow light, bot_02 blue), so the grader will judge on execution, not on the idea.
- We can't tell from the video whether they enforce evidence checks in code, test failure cases, or validate a shared contract. Do not claim they don't.

**How to position ours, truthfully:**
- "Our focus was correctness you can test: an evidence checklist and a provenance guard enforced in code, a validated contract between layers, and 120+ automated tests."
- "A demo view is planned for week 8 of our milestone plan, and the belief history already exists in the data, so a graph view can be built on it."
- The belief-chain diagram on slide 2 gives the same kind of visibility. It is drawn from a real run, so its ids and values match the log.

## 7. Likely questions and honest answers

| Question | Answer |
| --- | --- |
| Why no UI? | Our priority was a tested core: contracts, rules in code, evaluation. A demo view is planned for week 8. The belief history is stored, so a view can be built on it. |
| Are all three real layers connected? | Yes. Scenario A now runs end to end on Vyom's real memory, Asvin's simulated sensors and our agent. That is one run each for Scenario A and Scenario B, so we don't claim a pass rate yet. The full automated run across all ten tests comes next. |
| What did Scenario B show? | Memory held red (user, 0.9) and blue (bot_02, 0.8); the camera saw brown (0.9). The agent reported all three and recorded the camera reading, which memory marks as disputed. We do not claim it is resolved. We are checking with our evaluation teammate whether both stored views should have been downgraded, since they are perspectives. |
| How many of the 10 tests pass? | Do not give a number you can't back. Say: Scenario A (test 1) and the unknown-entity case (test 7 behaviour) are verified live on the procedural side; the full automated run across all ten is scheduled for weeks 6 to 7. |
| How do you know the agent doesn't hallucinate a reading? | It can't create one: sensor values come only from tool results, and when it updates memory from a sensor, the code takes the confidence from the real reading, not from the model. |
| What stops it from answering without checking? | The checklist in code. A premature answer is refused and the model is told what is missing; we saw this live. |
| What went wrong? | The model guessed the entity "route" instead of path_A, so memory returned nothing. Fix: give it the valid entity ids. Also a rate limit (HTTP 429) and a malformed tool call (HTTP 400): both now retry automatically. |
| Is your memory update safe? | Not fully. A downgrade followed by an update is two writes and there is no rollback. We know this and list it as a limitation. |
| Why this model? | An open-weight 20B reasoning model on Groq, temperature 0, with tool-calling support. Our original guidelines named an 8B model; we moved to this one. |
| What if sources disagree and neither is clearly better? | Vyom's rules keep the belief marked disputed instead of overwriting: for example a weak sensor (confidence below 0.5) cannot replace a strong historical belief. |
| How do you split the work and review it? | One layer per person. Small pull requests, a named reviewer, nobody merges their own work, and weekly rotating review pairs. |
| Commit counts look uneven | They are a rough indicator, not a measure of effort. Pull requests, reviews and design work carry the project too. |

## 8. Do not say

- Do not say all 10 tests pass, or give a pass count you can't show.
- Do not say all ten tests already run on the real layers. Only Scenarios A and B have run, once each.
- Do not say Scenario B "passes" or is "resolved": the new belief is disputed in memory.
- Do not say "3 of 3 on the real layers". It was 3 of 3 on stand-in layers, and the all-real-layers run is one run (Scenario A).
- Do not give the downgrade value as a fixed number: it varies (0.2 or 0.5) and any lower value is accepted.
- Do not criticise the other team's project. Say what yours does.

## 9. Before you go on

- Slides exported to PDF as a backup, and the PPT on a USB drive as well.
- The run log `agent_run_20261005T233840Z.json` saved on the laptop, in case someone asks to see the full record. Do not run a live demo: the API has a daily token limit.
- Both presenters know their slides without reading. Agree who answers which question.
- The room is D-LT10 and the slot starts at 4:00 PM.

## 10. Numbers you may quote

- Model: `openai/gpt-oss-20b` on Groq, temperature 0, step limit 10 model calls per question.
- 11 tools. Contract version 1.0. Fixed error codes: INVALID_ARGUMENT, NOT_FOUND, CONFLICT, SENSOR_UNAVAILABLE, STORAGE_ERROR, STEP_LIMIT, INTERNAL.
- Scenario A: map path_A clear (default_map, 1.0), LiDAR 12 cm, blocked, confidence 0.98.
- Real-memory run belief chain: b_000001 (map, 1.0) lowered to b_000004 (0.2), superseded by b_000005 (LiDAR, 0.98).
- Evaluation harness: a correct run passes 20 of 20 checks on S01; a deliberately wrong run fails 9.
- Commits, 6 October, all branches: Vyom 4, Asvin 6, Prem 6, Yash 5.
- Final submission: 15 November 2026. Week 6 starts 13 October.
