# Phase B adapter/interface compatibility

| Path | Actual public API | Safe execution in Phase B | Result / limit |
| --- | --- | --- | --- |
| Prem production LLMClient | Constructor client injection; chat(messages, tools, tool_choice) → LLMResponse | **Yes**, new Role 4 PremClientAdapter with fake SDK-shaped API | Real teammate client, fake_api mode, partial pipeline/client_chat_only; four outcomes observed |
| Prem scripted test LLM | ScriptedLLM(responses).chat(...) | **Yes**, through the same public adapter in a focused test | Reference fixture, scripted_llm mode; response and recorded input verified |
| Prem single tool proof | run_single_tool_call(llm, question, registry) → tool_calls/answer/messages | **No**, import requires absent contracts.models | No complete loop, reset/query context, snapshots, updates or claim-support metadata |
| Prem tool wrapper | call_tool(name,args,registry), currently read_lidar only; official ToolResult validation | **No**, absent official models | No validation bypass, fake contract or direct sensor execution substituted |
| Reference declarative adapter | Public reset/query/snapshot/upsert/history and committed receipts | **Yes**, retained reference backend | Real storage unavailable; snapshots and reset/reuse verified |
| Reference sensor adapter | Public reset/read_lidar/read_camera/state/revision | **Yes**, retained reference backend | Real environment unavailable; malformed and unavailable reads abort without fabricated facts |
| Reference procedural adapter | reset; run_query(query, QueryContext) → validated ResponseMetadata | **Yes**, deterministic reference policy | Does not fit Prem's client or single round directly; no emulated teammate agent |
| Vyom logger | No published API/file | **No** | Role 4 scoped logger remains evaluation-only |

`PremClientAdapter` lives under `evaluation/role4/integration/adapters/`. It calls
only backend.chat and records detached requests and actual normalised returns or
errors with paired client call IDs. It preserves argument-parsing error fields and
propagates exceptions instead of inventing an answer. It performs no tool dispatch,
evidence conversion, memory update, backend reset or run_query emulation. Its
integration_scope is partial_pipeline and pipeline_stage is client_chat_only.

The smoke exercises the unchanged real `procedural.llm_client.LLMClient` with
supported `client=FakeChatAPI(...)` injection. The Role 4 fake API follows the
same public SDK boundary used by Prem's existing tests; it is not a replacement
production module or official ToolResult contract. The recorded model string
phase-b-offline-fixture is a fixture identifier, not a provider model claim.

## Labels and observed outcomes

| Run | Backend provenance | Model mode | Scope / observation |
| --- | --- | --- | --- |
| Existing Phase 1 demo | All reference | scripted_fixture | S01 fixture trace; no live agent |
| Existing Phases 2–3 demos | All reference | deterministic_reference | Public reference integration; real teammate layers absent |
| Prem client smoke/plain reply | procedural=real; other layers unexercised | fake_api | One client request/response, fixed offline text |
| Prem client smoke/tool request | Same | fake_api | read_lidar ID/arguments parsed; no tool executed and no sensor evidence |
| Prem client smoke/malformed arguments | Same | fake_api | arguments_error retained with empty argument object; not a valid tool result |
| Prem client smoke/timeout | Same | fake_api | LLMClientError propagated and observed; no fallback answer |
| ScriptedLLM adapter test | reference (Prem test fixture) | scripted_llm | Existing public fake backend exercised, not production agent integration |

No mixed or complete three-layer teammate execution is claimed. Backend ownership
is separate from model execution. Fluent client text has no grounding/semantic
approval merely because transport passed. All human review status remains pending.
