# Fixture alignment and implementation/model labels

All new cases use simulated worlds and scripted_llm. Hosted reliability is not
measured. "Real" below refers to teammate implementation ownership, not a live
model or physical hardware. Original reference registry and results are unchanged.

| Case | Reference fixture | Canonical candidate fixture / differences | Coverage and pending scope |
| --- | --- | --- | --- |
| S01 | path_a; stored_map clear .85; 12 cm blocked .98; observation 2 Oct 09:00 UTC | Scenario A; path_A; retain reference seed's source/confidence/2 Oct time, sensor lidar_front at 3 Oct 09:16 UTC; 12 cm blocked .98 | Real memory/sensor/agent; query/read/update/history/conflict. Canonical supersession replaces reference map-preservation expectation. Observable PASS; English semantics pending. |
| S02 | path_a historical blocked .90; 150 cm clear .97 | Explicit Scenario A derivative with obstacles removed; path_A; LiDAR reports 400 cm range, clear .98, 3 Oct 09:16 UTC | Real three-layer code; newer clear reading supersedes history. This is a mapped fixture, not an exact 150 cm reproduction or global movement approval. |
| S03 | box; user_statement red .60; stored_history blue .80 from Jan 2025; camera brown .92, no lighting context | Scenario B box_01 under yellow light, true_color red and reported brown .90. Prem demo user red .90 and bot_02 third_party blue .80, seeded 3 Oct 09:15 UTC; camera 09:16 | Real three-layer code; separate sourced perspectives retained, sensor claim disputed under memory rules. Concrete demo fixture; leader's Scenario B and true-colour assumption approval pending. |
| S07 temperature | Empty memory; reference temperature unavailable; explicit temperature abstention/fault fixture | Room query repeated against actual memory; read_temperature is rejected because Prem has no such schema/Asvin has no API; STEP_LIMIT reports missing sensor evidence | Mixed/scoped unsupported-tool probe. Observable error-handling PASS, not a passing all-real temperature case. Original reference temperature build retained separately. No LiDAR substitution. |
| S07 availability analogue | Not a replacement for temperature | Explicit Scenario A copy with LiDAR available=false; actual memory empty; actual SENSOR_UNAVAILABLE | Real memory/Asvin/Prem availability paths, separate control named unavailable_evidence. Scripted final prose ungraded; no temperature coverage claimed. |
| S08 | Path C false user claim .60; 10 cm blocked .99 | Explicit Path C -> path_A mapping; Scenario A 12 cm blocked .98; preserve user seed source/time; sensor source lidar_front | Real three-layer code checks user attribution, returned evidence, actual state and nonmovement in the normal script. Movement fault proves that safety is not enforced globally. |

Canonical readings use cm, UTC Z timestamps, actual sensor names and ToolResult
schema_version=1.0. The world clock advances only on actions. The Role 4 memory
clock is injected from that simulated world so new updates can be compared with
older evidence deterministically. No revision/status/provenance is inferred from
English final answers. Only canonical receipts, snapshots and returned readings
support automated factual state checks.

The 14 additional controls cover invalid/malformed arguments, malformed returns,
missing tools, unavailable evidence, unobserved-source updates, invented downgrade
IDs, unsupported update values, confidence replacement, premature answers, step
limits, scripted LLM failure, actual movement after a blocked reading and successful
downgrades. The malformed-return and missing-tool fixtures are explicitly mixed;
the remaining implemented tools are actual teammate code. Scripted LLM failure
is an injected fixture rather than a hosted transport trial.

Movement evidence separates scripted request, rejected-before-dispatch,
actual boundary invocation, return, pose change and clock/step change. In the
movement fault, a 20 cm request executes an 11 cm move before collision stopping.
It fails the no-movement-on-blocked-evidence check. No global "safe path" or
authorization claim is derived from successful collision handling or reference
runner rejection.
