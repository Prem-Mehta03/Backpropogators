# First end-to-end run: failure list

Runs on 2026-10-05 with `openai/gpt-oss-20b` and stub tools. Round 1 (3 runs, entity list
hidden): `evaluation/logs/agent_run_20261005T124900Z.json`, `...T124944Z.json`,
`...T125008Z.json`. Round 2 (3 runs, entity list on): `...T131617Z.json`, `...T131649Z.json`,
`...T131719Z.json`. "Layer" is where the failure STARTED (Guidelines section 8).

What went right in all 6 runs: called query_belief and read_lidar, answered "No, the route is
not clear", copied the sensor values and invented nothing. In round 2 the conflict (map "clear"
versus LiDAR 12 cm blocked) was seen and explained in 3 of 3 runs.

| # | What happened | Log file and step | Layer | Owner | Fix | Status |
|---|---|---|---|---|---|---|
| 1 | Model queried subject `route` instead of `path_A`; NOT_FOUND, conflict never seen (round 1, 3 of 3) | round 1, step 1 | procedural (contributing: declarative, NOT_FOUND names no known subjects) | Prem; Vyom for the message text | Entity list in the system prompt from config (`known_subjects`); ask Vyom to list known subjects in NOT_FOUND | fixed: round 2 used `path_A` in 3 of 3 runs |
| 2 | Model added a made-up filter `perspective: agent_sensor` (round 1, run 2) | `...T124944Z`, step 1 | procedural | Prem | Tool descriptions and prompt: leave optional filters out on the first lookup | fixed: no filters in round 2 (3 of 3) |
| 3 | After NOT_FOUND the model never retried (round 1) | round 1 | procedural | Prem | Prompt: retry once with a listed id and no filters | partly closed: round 3 (`box_99`) queried once, tried the camera, then said plainly that evidence is missing and wrote nothing. `box_99` is not a listed id, so no retry was expected |
| 4 | Raw JSON envelope pasted into the answer (round 1, run 1) | `...T124900Z` | procedural | Prem | Answer format: never paste raw tool output | fixed: none in round 2 |
| 5 | No downgrade or update after contradicting evidence | all | procedural | Prem (with Vyom's conflict rules) | Evidence checklist, provenance guard and conflict-resolution prompt | fixed: round 3, 3 of 3 runs did query_belief, read_lidar, downgrade_belief, update_belief in order, all ok, no nudges |
| 6 | Confidence written as "100 %" and "98 %" (round 2, run 2) | `...T131649Z` | procedural | Prem | Answer format: decimals, never percentages | fixed: round 3 answers use decimals (1.0, 0.98) in 3 of 3 |
| 7 | Dates in the answer used non-breaking hyphens (round 2, 3 of 3; also seen on the first LiDAR run) | all round 2 | procedural | Prem | `normalize_answer_text` in code; the log field `answer_normalized` shows when it fired | fixed: round 3 `answer_normalized` was true in 3 of 3, so the code is still needed |
| 8 | Groq 429 (tokens per minute, limit 8000) ended the `box_01` run after 3 tool calls, before any answer | `...T145043Z` | procedural (LLM client) | Prem | `LLMClient` waits the time the server asks for and retries up to 4 times; other errors are not retried | fixed in code; verified: `box_01` re-run finished (2 of 3 later runs) |
| 9 | Groq 400 `tool_use_failed`: the model wrote a malformed `update_belief` call; the run ended after `downgrade_belief` had already run, leaving memory half-updated | `...T151117Z` | procedural (model slip, LLM client) | Prem | `LLMClient` retries up to 2 times at temperature 0.3; a run that still fails stays half-written (writes are not atomic, no rollback tool) | fixed in code, watch for repeats |
| 10 | `box_01` answer said "No conflict resolution needed" although red, blue and brown disagreed and one belief had been downgraded; it did not say which source it trusts | `...T150656Z`, `...T151311Z` | procedural | Prem | Prompt v4: state every disagreement, say which is trusted and why, report writes exactly | fixed in prompt, verify on real run |

No declarative or sensorimotor failures were observed, but both layers were stubs.
Owners: declarative = Vyom, sensorimotor = Asvin, procedural = Prem, test harness = Yash.
