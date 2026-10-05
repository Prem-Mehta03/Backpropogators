# Declarative Layer Report Outline

## Purpose

Explain how I, Agent stores claims with provenance, retrieves them by perspective, and applies evidence-priority rules. Use the v1.0 models and declarative implementation as the source of truth.

## 1. Belief and boundary contracts

- Describe the `Belief` fields: schema version, ID, subject, predicate, object, source, confidence, timestamp, perspective, status, validity interval, and supersession link.
- Describe `SensorReading`, `ToolError`, and success/failure `ToolResult` envelopes.
- Explain strict field validation, fixed enums, UTC timestamps ending in `Z`, confidence range, and `b_######` IDs.

## 2. Provenance and storage

- Explain SQLite as the provenance/history store and NetworkX as the graph view.
- Describe how a successor points to the record it supersedes and how history queries retain prior evidence.
- Explain reset behavior, stable ID allocation, and persistent-database setup.

## 3. Memory API and perspectives

- Document `add_belief`, `query_belief`, `get_belief`, `get_belief_history`, `get_source`, `update_belief`, `downgrade_belief`, and `detect_conflict`.
- Explain default current-belief queries and explicit perspective queries, including superseded historical records.
- Describe the `user`, `agent_sensor`, `historical`, and `third_party` perspectives.
- Explain the caller-supplied `bot_02` fixture helper; use the value agreed by the team for Scenario B.

## 4. Conflict and evidence priority

- Explain the code paths for strong current sensor evidence, low-confidence evidence, same-perspective updates, and live sensor disagreement.
- Describe the `accept`, `replace`, and `dispute` policy results and their reasons.
- Explain the missing-provenance confidence cap and user-source attribution.
- Clarify the sequence the agent/tool wrapper uses for Scenario A: detect conflict, lower confidence when required, update from the live reading, then cite both records.

## 5. Scenario A walkthrough

- Starting map claim: `path_A/status = clear` with historical provenance.
- Current observation: `lidar_front` reports `12 cm`, `blocked`, confidence `0.98`.
- Show the before/after graph and the `supersedes` chain in `scenario_a_belief_graph.mmd`.
- Replace the conceptual figure with a snapshot captured from the integrated deterministic run.

## 6. Logging and errors

- Explain JSONL event capture for tool calls and committed belief changes.
- Show the test-log fields: question, state before, tool calls, state after, answer, expected behavior, checks, and result.
- Summarize the fixed error-code list and the rule that layer functions return envelopes rather than leaking exceptions.

## 7. Integration and verification

- Report Role 1 contract/declarative/logger test results after running them in the repository environment.
- State the precise mapping, if any, from the canonical v1.0 API to Yash's scoped Role 4 reference ports.
- Resolve the S01 preservation-versus-supersession policy difference with the team before claiming integrated evaluation coverage.
- Include peer-review changes and the final code-backed graph capture.
