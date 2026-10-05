# Phase B inputs and API compatibility

**New Phase B update:** the available Prem client path now has an observed offline
compatibility adapter and four verified fake-API outcomes. Single-tool integration
remains blocked; no approved contracts or sensor fixture appeared in this clone.
See [blocker diagnosis](phase_b_collection_blockers.md),
[compatibility matrix](phase_b_compatibility_matrix.md), and
[historical reuse decisions](historical_phase4_reuse_matrix.md).
The sections below retain the Phase A handoff context; its request for permission
to start Phase B was satisfied by the user's Phase B instruction.

Next inputs are unchanged: Vyom's approved ToolResult/models and logger, Asvin's
public sensor/environment APIs and approved offline fixture, and Prem's agent
entry point/reset/response metadata. Prem and Asvin must resolve the current
sensorimotor.stub test dependency before the single-tool suite can collect.
Hosted credentials are not required for the next offline integration check.
For authorized Phase C, reuse historical S07 selectively instead of rebuilding
it; retain S01/S02/S03/S08 checks and obtain human review separately.

These are findings and requests to discuss; no teammate was messaged in Phase A.
Keep team-owned schemas authoritative. Do not create fake top-level contracts to
make blocked tests pass.

## Published Prem code

`procedural.llm_client.LLMBackend.chat(messages, tools=None, tool_choice=None)`
returns `LLMResponse(content, tool_calls, finish_reason)`. Each ToolCall has id,
name, argument dictionary and optional parsing error. `LLMClient(client=...)`
accepts an injected API for offline tests. Without injection it needs a key and
the currently missing `openai` package; hosted scripts were not run. The default
model string in checked-out code is `openai/gpt-oss-20b`; its header describes an
8B default, so the documentation is inconsistent. This records local code, not
current provider availability.

`run_single_tool_call(llm, question, registry)` makes at most one tool round, then
requests a text answer with `tool_choice="none"`. It returns tool_calls, answer,
messages and tool_was_called, without reset, run_query, claim-support metadata,
memory snapshots or belief updates. It is a proof, not the planned agent loop.
`call_tool(name, args, registry)` supports `read_lidar(direction="front")`, requires
`contracts.models.ToolResult` and returns an envelope with tool/ok/data/error/
timestamp. Error codes observed in code are INVALID_ARGUMENT, INTERNAL and
SENSOR_UNAVAILABLE. Exact approved schema and allowed code list are unavailable.

The Role 4 reference API instead uses `reset(scenario_id)` and
`run_query(query, QueryContext)` with an instrumented `context.tools.call(...)`.
Evidence needs IDs, subject/predicate/value, source/perspective/confidence/time,
paired call/return events, and update receipts. Prem's single round cannot yet
satisfy the full S01 memory-query/sensor/update flow or structured claim grading.
Phase B must map the real envelope and actual observed calls, never reconstruct
invented events or infer claim support from a passing fixture.

## Inputs by owner

| Owner | Needed input | Current availability / mapping issue |
| --- | --- | --- |
| Vyom | Approved contracts/models.py, schema version, validators and ToolResult/Error examples | Absent; Prem imports them; scoped dataclasses are reference-only |
| Vyom | Public memory reset/query/snapshot/upsert/history APIs and before/after receipts | No declarative implementation; database/graph must remain internal |
| Vyom | Logger API, event schema, timestamp/run-ID rules, error retention | Logger absent; scoped Role 4 JSONL logger records evaluation fixtures only |
| Asvin | Published sensors/environment reset/snapshot/revision APIs and approved scenario configs | Absent; teammate tests import sensorimotor.stub; do not copy placeholder |
| Asvin | Sensor envelope fields, unit/direction/availability semantics and evidence conversion | Planned sensors.py returns ToolResult; adapter mapping needs approved samples |
| Prem | Current agent/state code, injected registry/reset behavior, step limit and response interface | Only single_tool_call proof is published; no deep integration in Phase A |
| Whole team | Team_Guidelines, role documents, agreed formatting/test commands and review rubric | Referenced guidelines/pyproject absent; black/ruff unavailable locally |

Public reference memory ports are documented in
`evaluation/role4/contracts/declarative.py`; sensor ports in `sensorimotor.py`;
procedural ports in `procedural.py`. They are integration proposals, not changes
to Vyom's contracts. Keep raw returns and fail on malformed/missing required
fields. Agree null-versus-absent provenance, time zones, confidence thresholds
(currently 0.7), observation age (300 simulated seconds), error envelopes and
revision semantics before mapping real code.

## Phase B objective

Run the available real teammate procedural code with a scripted LLM, once its
approved dependencies are published; add a thin explicit adapter and boundary
checks. Keep references for missing memory/sensors, report layer ownership
separately from model mode (`scripted_llm`, `hosted_llm`, or other measured mode),
and label mixed runs accurately. Obtain published teammate inputs and explicit
approval to start Phase B. Hosted reliability trials and S07 implementation
remain outside Phase A. Human prose review is still required.
