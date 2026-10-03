# Representative New Phase A evidence

Generated from this clone by scripts/run_role4_phase2_demo.py on 3 October 2026.
These are current deterministic reference runs, not historical source evidence,
teammate integration, hosted model reliability or human-reviewed prose.

- S01_integrated_valid_trace.jsonl: passing public-adapter trace, 20/20 checks.
- S01_missing_lidar_trace.jsonl: injected procedural fault, 11/20 checks, expected FAIL.
- S01_malformed_sensor_error.json: missing confidence rejected, evaluated=false.

Full outputs are ignored under evaluation/logs/role4. The three offline scripts
reproduce them with fixed observations/IDs and fresh UTC event timestamps.
Phases 1-3 summary outcomes are recorded in ../phase_a_verification.json.
