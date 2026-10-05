# Declarative Layer

## What the layer owns

- Shared v1.0 Pydantic contracts for beliefs, sensor readings, tool errors, and results.
- SQLite provenance/history plus a NetworkX belief graph.
- Memory queries by subject, predicate, and perspective.
- Conflict detection and evidence-priority decisions in code.

## Scenario A: map clear, LiDAR blocked

The historical map says `path_A/status = clear`. The newer `lidar_front` observation is `12 cm`, `blocked`, confidence `0.98`. The memory API retains provenance and history, applies the v1.0 priority rule, and returns the updated or disputed belief in a `ToolResult` envelope. A caller can lower the map belief first with `downgrade_belief`; the lowered claim remains in history when the sensor-backed belief supersedes it.

## Rules enforced by code

- Sensor confidence at least `0.6` can replace older historical evidence.
- Sensor confidence below `0.5` cannot replace a historical belief at `0.8` or above; keep the sensor evidence disputed.
- Disagreeing live sensors remain disputed.
- Missing provenance caps confidence at `0.5`; user claims remain attributed to the user.

## Boundary

Other layers use `contracts/` and the published memory API. The procedural layer does not access SQLite or the NetworkX graph directly.

## Presenter note

Use `scenario_a_belief_graph.mmd` as the conceptual before/after sequence. Its example downgrade value is illustrative; replace the diagram with captured run data when the full integration is available. Check `integration_notes.md` before describing the Role 4 reference harness as integrated.
