# Canonical API and policy mapping

Official contracts remain strict and unchanged. Adapters live only under Role 4;
composition and cross-layer imports remain in its integration root.

| Reference field / convention | Canonical handling |
| --- | --- |
| value | Seed as `object`; canonical raw payload retained alongside display `value` |
| observed_at, aware ISO timezone | Normalize explicitly to UTC `timestamp` ending in Z; reject naive timestamps |
| path_a_map, path_c_user | Capture actual allocated `b_######` in an alias map; never send reference IDs to tools |
| path_a, box, path_c | Explicit fixture mapping to path_A, box_01, path_A respectively; Path C remapping is documented scenario adaptation |
| old reference has no validity/status fields | Preserve raw schema_version/status/valid_from/valid_to/supersedes; the BeliefState projection is display-only |
| query_memory/upsert_belief/reset port | Inject actual canonical tool methods instead; do not pretend the APIs are identical |
| reference sensor reading_id/environment_revision | Keep canonical reading unchanged; use boundary request IDs and actual world step/time snapshots instead of fabricating canonical fields |
| structured reference answer claims | No canonical AgentResult equivalent; set structured_answer_claims=null and human semantics pending |

Actual APIs exercised:

- `BeliefMemory(database=None, clock=None, event_callback=None)` with isolated
  in-memory SQLite, actual world clock and official logging callback. Seeding
  uses `add_belief(subject, predicate, object, source, confidence, perspective,
  timestamp=None)`; `seed_bot_02_record` is used for the concrete demo fixture.
- `query_belief(subject, predicate=None, perspective=None)`,
  `get_belief_history(subject, predicate=None)`,
  `update_belief(subject, predicate, object, source, confidence, perspective,
  reason, timestamp=None)`, `downgrade_belief(belief_id, new_confidence, reason)`,
  `detect_conflict(subject, predicate)`. Results are validated v1.0 ToolResult
  dictionaries. Snapshot/close are local harness lifecycle operations.
- `create_sensorimotor(scenario, seed)` accepts a name or explicit configuration
  mapping. Each run calls `env.reset()` and uses the six actual bound functions
  from `tool_registry()`. Environment is simulated; sensors are teammate code.
- Asvin's `reading_to_evidence` maps LiDAR to path_A/status and camera to
  object_id/color. The Role 4 boundary validates ToolResult and SensorReading
  before using it. Unknown/error/failed readings create no evidence.
- `run_agent(question, llm, registry, max_steps=10, system_prompt=None,
  known_subjects=None, required_evidence=...)` receives an injected scripted
  backend. AgentResult exposes answer, tool_calls, messages, model_calls, error,
  answer_normalized and evidence_nudges. It logs via Python logging and records
  actual guard decisions; it does not emit verified answer claims or confidence.
- Official `EvaluationLogger.log_event` captures actual committed memory callbacks
  and observed events. `write_test_log` contains actual state/tool outcomes and
  observable evaluation checks. Existing Role 4 TraceRecorder/EventLogger,
  EvaluationResult, BeliefState, scenario loading and JSON/JSONL utilities are
  reused. The old reference evaluator/policies are untouched.

Prem's `build_tool_registry(use_real=True)` may still fill absent tools with test
fakes. Before wrapping tools the Role 4 root checks every source and actual bound
owner against the constructed memory/sensor/action instances. Malformed-envelope
and missing-tool probes are explicit mixed fault fixtures. All-real-labelled
runs contain no fallback fake. Malformed raw returns stay in boundary logs even
when Prem converts them to a canonical INTERNAL envelope.

Canonical policy is separately named `canonical_teammate_v1` and checks observable
state/evidence bindings. Based on `declarative/conflicts.py`, owner tests and Role 1
integration notes, newer agent_sensor evidence with confidence >=0.6 supersedes a
contradictory historical belief. The old record is closed with status= superseded,
valid_to and a successor link; it is retained, not required unchanged. An explicit
downgrade control also exercises lower-confidence history successors. No change
is made to the historical reference S01 policy that requires preserving its map.

Successful canonical sensor updates are checked against returned
subject/predicate/object/source/confidence/perspective and actual committed
receipts. Unresolved user/third-party/sensor priority remains disputed according
to memory rules; no invented winning perspective or passing human decision is
added. Answer text is a scripted fixture, even when calls adapt to actual returns.
Observation-based memory checks do not imply independent English comprehension.
