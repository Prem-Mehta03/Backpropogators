# 3a. Declarative layer

The declarative layer stores beliefs as strict, versioned records. Each belief carries an identifier, subject, predicate, value, source, confidence, UTC timestamp, perspective, status, validity interval, and optional supersession link. Contract models accept both v1.0 records and v1.1 records; newly created records use v1.1. SQLite keeps the full history, while NetworkX provides an in-memory graph view.

Beliefs retain their perspective: `user`, `agent_sensor`, `historical`, or `third_party`. User and third-party claims remain attributed side by side and do not dispute another perspective. Newer evidence from the same perspective supersedes its predecessor, closing the predecessor's `valid_to` at the successor timestamp. Current queries return newest evidence first; history queries retain the full timeline.

Evidence thresholds live in `contracts/policy.py` so layers can share one source of truth. A sensor reading below 0.5 cannot replace a belief at or above 0.8. Live sensor evidence at or above 0.6 can replace an older conflicting historical belief. Conflicting live distance sensors produce a disputed record. The resolver compares timestamps with `>=`, subject to the stored validity-window bounds; it does not use belief IDs to break timestamp ties.

Beliefs with no source are capped at 0.5 confidence on every memory write path and emit a `missing_provenance` event through the configured evaluation callback. They remain stored for auditability, but their missing source is explicit. Superseded records remain available; updates do not erase evidence.

Each SQLite insert is one committed write. Closing a belief and inserting its successor runs in one transaction, so a failed supersession leaves neither a half-closed prior row nor a missing successor. A two-step agent operation that separately downgrades and then records a sensor belief can still be interrupted between calls; that cross-call limitation belongs in the report.

The stale threshold is seven simulated days. Newer evidence from the same perspective marks an older belief stale; evidence more than seven days newer also marks the older record stale. Staleness is derived from timestamps and does not add a contract field. Deterministic fixture setup is exposed through `seed_for` for the map-blocked, T04, T05, T06, T09, T10, and B-approach scenarios.

The figure in `scenario_a_belief_graph.mmd` illustrates the provenance chain: the original map claim is superseded by its downgraded successor, which is superseded by the current LiDAR claim. Integrated run IDs and timestamps should replace illustrative timestamps when the final evaluation runner is available.
