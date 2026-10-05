# Role 1 Integration Notes

This page records interface differences visible in the repository clone on 5 October 2026. `contracts/` and `declarative/` implement the official v1.0 Team Guidelines supplied with the project. Yash's `evaluation/role4/` ports are explicitly labeled reference interfaces, not approved shared contracts; these notes are for team alignment, not a request already sent to anyone.

## Canonical contract versus Role 4 reference

- The canonical `Belief` uses `schema_version`, `object`, `timestamp`, `valid_from`, `valid_to`, and a declarative `b_######` ID.
- Role 4's internal `BeliefState` uses `value`, `observed_at`, and scenario IDs such as `path_a_map`.
- The official memory tool names are `query_belief`, `get_belief_history`, `update_belief`, `downgrade_belief`, and `detect_conflict`. Role 4's proposed port uses `reset`, `get_beliefs`, `get_belief_snapshot`, and `upsert_belief`.
- Do not loosen the canonical contract to accept reference-only fields or IDs. Add and review a narrow adapter when the owners approve the mapping.

## Scenario A policy difference

The official v1.0 rules say a sufficiently confident newer sensor can supersede older historical evidence. The Role 4 S01 reference currently requires the old map belief to remain unchanged and adds a separate sensor belief. These are different expected state transitions. The canonical memory implementation follows the official rules. Agree on the intended behavior with Vyom, Prem, and Yash before treating the Role 4 S01 reference result as a conformance test for this API.

## Procedural envelope compatibility

The current `procedural/tools.py` constructs ToolResult mappings without `schema_version`. The canonical v1.0 model requires that field, as the Team Guidelines do. Prem should add it at the point where he constructs success/error envelopes; making the canonical field optional would weaken the shared contract.

## Scenario B provenance detail

The source plan names `bot_02` as the third-party source but does not specify the third-party claim's subject, predicate, object, confidence, or timestamp. `seed_bot_02_record()` therefore requires those details from the caller instead of inventing a Scenario B fact. The generic test record is marked as a fixture only.

## Current verification boundary

Run the Role 1 test files listed in the repository README after installing the repository requirements. Full project discovery still has separate missing sensor/procedural integration inputs documented by Role 4; those are not represented as passed by these Role 1 files.
