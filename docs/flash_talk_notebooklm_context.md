# Team BackPropogators: I, Agent. Mid-project flash talk (source for a 4-slide deck)

## 0. Instructions for the deck generator

**Format**
- Exactly **4 slides**, 16:9, for a talk of 3 to 4 minutes given by one or two presenters.
- Audience: the course instructor and teaching assistants (technical).
- Use only facts from this document. Do not invent numbers, dates, names, test results or features.
- Put the speaker script (section 6) in the speaker notes. Do not put it on the slides.

**Visual style: professional, calm, generous white space**
- Overall look: clean and modern, like a research or engineering team briefing. Light background (white or very light grey) for slides 2 to 4; a dark navy cover for slide 1.
- Colour palette, used consistently on every slide:
  - Navy `#0B1F3A`: cover background, titles.
  - Teal `#0F766E`: primary accent (lines, highlights, "completed" marks).
  - Indigo `#3730A3`: the Declarative layer.
  - Teal `#0F766E`: the Procedural layer.
  - Amber `#B45309`: the Sensorimotor layer, and warnings or "lowered" values.
  - Slate `#334155`: body text. Light grey `#F1F5F9`: card backgrounds. Mint `#ECFDF5`: highlighted cards.
- Typography: one clean sans-serif family (Inter, Segoe UI or Calibri). Slide title 36 to 40 pt, headings 22 to 26 pt, body at least 18 pt. Never go below 16 pt.
- Layout: every slide has a title, a one-line subtitle, and **at most three content blocks** arranged in a clear grid with equal margins. Use cards with rounded corners and thin borders. At most 5 short bullets per block, each under 14 words. No walls of text, no clip art, no decorative gradients.
- Use simple line icons only where they help (a brain, a database, a sensor). Keep them small and in the layer colour.
- The belief-chain diagram image supplied with this document must appear on slide 3, uncropped and readable. Do not redraw it.

## 1. Slide 1: cover and problem

**Title:** I, Agent
**Subtitle:** An AI agent that checks what it believes against what it observes
**Team name (large, below the title):** Team BackPropogators
**Meta line (small):** Mid-project flash talk · 6 October 2026

**Team strip (small cards, one per member, with role in the layer colour):**
- Vyom: Declarative layer (beliefs and provenance)
- Prem Mehta: Procedural layer (LLM reasoning and tools)
- Asvin: Sensorimotor layer (simulated sensors and actions)
- Yash: Evaluation and integration

**Problem block (a highlighted card, "The problem"):**
- LLM agents act on beliefs they cannot verify.
- They trust stored or user-given information, even when the world has changed.
- They confuse whose belief is whose: the user's, their own senses, history, or a third party.
- Result: confident answers that are not grounded in evidence.

**Example line (one sentence, under the problem card):** The map says the path is clear, but the LiDAR sees an obstacle 12 cm ahead. Which source should the agent trust, and can it explain why?

**Our goal block (a second card, "What we are building"):** An agent that checks evidence before answering, notices when sources disagree, updates its belief state when appropriate, and explains which source supports its conclusion.

## 2. Slide 2: architecture

**Title:** Three isolated layers: what it believes, how it reasons, what it senses
**Subtitle:** The layers never import each other. They talk only through tools and one validated JSON contract.

**Main graphic: three stacked or side-by-side layer cards connected by arrows, with a bar labelled "Contract v1.0: 11 tools, one validated envelope" running between them.**

| Layer | Owner | Colour | What it holds or does |
| --- | --- | --- | --- |
| Declarative: the knowledge | Vyom | Indigo | Belief graph (NetworkX) and provenance log (SQLite). Every belief has a source, confidence, timestamp and perspective: user, agent_sensor, historical or third_party. Evidence-priority and conflict rules live here. |
| Procedural: the brain | Prem | Teal | The LLM runs a reasoning-and-acting loop and chooses tools. It enforces an evidence checklist and a provenance guard in code. |
| Sensorimotor: the senses | Asvin | Amber | A simulated robot environment: LiDAR, camera, position, move and turn. Readings change when the robot acts. |

Below the graphic, one thin strip of three short "design rules" in separate small cards:
1. **One contract:** every tool returns the same validated envelope (schema_version, tool, ok, data, error, timestamp).
2. **Rules live in code, not prompts:** the model never edits storage directly and never invents a reading.
3. **Check before answering:** the agent must consult memory and a sensor first.

Small footer line: 11 tools: 5 memory tools (query, history, update, downgrade, detect conflict) and 6 sensing and action tools (LiDAR, camera, position, forward, backward, turn).

## 3. Slide 3: progress and live evidence

**Title:** Weeks 1 to 5 complete, and the agent resolves a real conflict
**Subtitle:** Milestones delivered through 4 October, with a live result on a hosted open-weight model

**Left block: milestone timeline (a compact horizontal or vertical stepper with checkmarks in teal, one line per week):**

| Week | Dates | Milestone | Status |
| --- | --- | --- | --- |
| W1 | 31 Aug to 6 Sep | Contracts and foundations: JSON contracts v1.0, repository, model and API chosen, 10 test cases defined | Completed |
| W2 | 7 to 13 Sep | Each layer runs on its own: storage, mock environment, LLM client, first ReAct loop, test harness | Completed |
| W3 | 14 to 20 Sep | Tools and unified agent loop: tools validated, step limit, error handling | Completed |
| W4 | 21 to 27 Sep | Scenario A (map versus sensor): conflict detection, priority rules, tests 1 and 2 | Completed |
| W5 | 28 Sep to 4 Oct | Scenario B (three perspectives), tests 3, 7 and 8, mid-project build tagged | Completed |
| Next | 13 Oct onward | Instructor feedback, low-confidence and missing-provenance rules, remaining tests | Upcoming |

**Main block: the belief-chain diagram image (supplied).** It shows one real run of Scenario A: the map belief (clear, confidence 1.0) is lowered to a successor (0.2), and the live LiDAR reading (blocked, 12 cm, confidence 0.98) becomes the active belief. Nothing is deleted: each change adds a new belief that supersedes the old one. Caption under the diagram: "Live run, openai/gpt-oss-20b, temperature 0, 5 model calls. All three layers real: Vyom's memory, Asvin's simulated sensors, our agent."

**Evidence strip (five small result cards, equal width, one fact each):**
1. **Scenario A: 3 of 3 live runs** on stand-in layers, then run end to end on all three real layers. The answer is "No, my route is not clear", citing both the map and the LiDAR.
2. **Scenario B: three views of one box.** Memory holds red (user, 0.9) and blue (bot_02, 0.8). The camera sees brown (0.9). The agent reports all three sources and records the camera reading as disputed. Run once on all three real layers.
3. **Unknown object:** asked about an object that exists nowhere, the agent says it has no evidence and writes nothing to memory.
4. **Enforced in code:** an answer is refused until memory and a sensor have both been checked, and a belief can only be downgraded using an id that memory returned.
5. **Tested:** more than 120 automated procedural tests with no network; the evaluation harness passes a correct run on 20 of 20 checks and fails a deliberately wrong run on 9.

**Status line (small, at the bottom):** Scenarios A and B have each run once end to end on all three real layers. The remaining work is the full automated test run and the perspective rules.

## 4. Slide 4: contributions and next steps

**Title:** Four roles, one tested system
**Subtitle:** Who built what, how we work, and what comes next

**Main block: contributions table (one row per member; the member's role colour on the left edge of each row):**

| Member | Role | Contributions | Commits |
| --- | --- | --- | --- |
| Vyom | Declarative layer | Belief and provenance schema; contracts package with validated models; NetworkX graph and SQLite storage; memory API; conflict detection and evidence-priority rules; perspective support | 4 |
| Asvin | Sensorimotor layer | World schema; deterministic mock environment; LiDAR, camera, position, move and turn tools; Scenario A and B worlds; lighting model; sensor-to-belief adapter | 6 |
| Prem Mehta | Procedural layer | LLM client with retries; 11 validated tool wrappers; agent state and reasoning loop with step limit; system prompt and evidence policy; evidence checklist and provenance guard; 120+ tests; live-run failure analysis | 6 |
| Yash | Evaluation and integration | Repository skeleton and pytest setup; test harness and log format; the 10 test cases with pass criteria; contract-conformance tests; integration and evaluation demos | 5 |

Table footnote: Commits are `git shortlog` counts across all branches on 6 October 2026. They are a rough indicator, not a measure of effort.

**Two small blocks under the table, side by side:**

*How we work*
- One layer per person, small reviewed pull requests, nobody merges their own work.
- Weekly rotating code-review pairs.
- A team gate at the end of each week.

*What comes next*
- Week 6 (from 13 Oct): instructor feedback, low-confidence and missing-provenance rules.
- Remaining tests: 4, 5, 6, 9 and 10; all 10 automated by week 7.
- Reliability runs, architecture verification report and final demo; submission on 15 November.

**Closing line (small, centred):** Thank you. Questions welcome.

## 5. Facts you may quote

- Model: `openai/gpt-oss-20b`, an open-weight 20-billion-parameter reasoning model served by Groq, temperature 0. Step limit: 10 model calls per question.
- Contract version 1.0. Fixed error codes: INVALID_ARGUMENT, NOT_FOUND, CONFLICT, SENSOR_UNAVAILABLE, STORAGE_ERROR, STEP_LIMIT, INTERNAL.
- Scenario A: map belief path_A status = clear (source default_map, confidence 1.0); LiDAR reads 12 cm, status blocked, confidence 0.98.
- Real-memory run belief chain: b_000001 (clear, 1.0) lowered to b_000004 (clear, 0.2), superseded by b_000005 (blocked, 0.98, lidar_front).
- Ten evaluation tests: 1 map clear and LiDAR blocked; 2 map blocked and LiDAR clear; 3 three perspectives; 4 very low sensor confidence; 5 two sensors disagree; 6 stale historical belief; 7 no belief or sensor data; 8 false user information; 9 missing provenance; 10 world changes during reasoning.
- Final submission: 15 November 2026.

## 6. Speaker script (about 3 minutes 20 seconds, for the speaker notes)

**Slide 1, about 25 seconds.** "We are Team BackPropogators, and our project is I, Agent. Language-model agents act on beliefs they can't verify. They trust a stored map or a user's claim even when the world has changed, and they mix up whose belief is whose. Our goal is an agent that checks its evidence before answering, notices when sources disagree, updates what it believes, and explains which source supports its conclusion."

**Slide 2, about 55 seconds.** "We split the system into three isolated layers. The declarative layer, built by Vyom, stores beliefs together with their source, confidence, time and perspective. The procedural layer, which I built, is the language model in a reasoning-and-acting loop that chooses tools. The sensorimotor layer, built by Asvin, is a simulated robot with LiDAR, a camera and movement. The layers never import each other. They only talk through 11 tools and one validated JSON envelope. And our rule is that rules live in code, not in prompts: the model never writes to storage on its own, never invents a reading, and can't answer until it has checked both memory and a sensor."

**Slide 3, about 1 minute 25 seconds.** "We have completed the milestones for weeks one to five. Here is the key test. The map says the path is clear, but the LiDAR reports an obstacle at 12 centimetres, and we ask the agent: is your route clear? In the diagram you can see what it did. It looked up its stored belief, which was clear at confidence 1.0. It read the LiDAR, noticed the two disagree, lowered the map belief to 0.2, and recorded the live reading as a new belief at 0.98. Nothing is deleted: each change supersedes the one before. It then answered that the route is not clear and cited both sources. This worked in three out of three live runs on stand-in layers, and again with all three real layers connected. When we asked what colour a box is, memory said red and blue, the camera said brown, and the agent reported all three sources and marked the new belief as disputed. When we asked about an object that doesn't exist, it said it had no evidence and wrote nothing. These checks are enforced in code, covered by more than 120 automated tests, and our evaluation harness passes a correct run on twenty of twenty checks and fails a deliberately wrong one. Both scenarios have run on all three real layers together: Vyom's memory, Asvin's simulated sensors and our agent. The remaining work is the full automated test run and the perspective rules."

**Slide 4, about 40 seconds.** "Each role owned one layer. Vyom built the belief schema, storage and conflict rules. Asvin built the simulated world and the sensor adapter. I built the model client, the tools, the reasoning loop and the checks that enforce the evidence policy. Yash built the test harness and the integration. The commit counts are on the slide, and they are only a rough indicator, because we work in small reviewed pull requests with weekly rotating review pairs. Next we handle instructor feedback, automate the remaining tests, and prepare the verification report and final demo for submission on 15 November. Thank you."
