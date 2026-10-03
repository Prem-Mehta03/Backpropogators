# Backpropogators

## Role 4 evaluation foundation — New Phase A

Yash's Phase 1–3 evaluation infrastructure is scoped under `evaluation/role4/`,
with regression fixtures/tests in `tests/role4/` and three offline demo scripts.
It uses only Python's standard library (Python 3.10+). Shared `contracts/` and
Vyom's `evaluation/logger.py` remain owner-controlled; the scoped reference
ports/logger do not replace them. All demo layers are deterministic references.

From this repository root:

```powershell
python -B -S -m unittest discover -s tests/role4 -q
python -B -S scripts/run_role4_phase1_demo.py
python -B -S scripts/run_role4_phase2_demo.py
python -B -S scripts/run_role4_phase3_demo.py
# Available teammate client tests: uses installed pytest and injected fake APIs.
python -B -m pytest -p no:cacheprovider tests/procedural/test_llm_client.py -q
# Full offline discovery: currently reports missing shared contracts/sensor module.
python -B -m pytest -p no:cacheprovider tests -k 'not live' -q
```

Always exclude `live` tests for offline runs, even when a key is configured.
Demos write ignored reproducible outputs to `evaluation/logs/role4/phase1-3`.
Expected injected failures and malformed-payload rejections are demo successes;
they do not represent passing agent behavior. Human semantic review is pending.

See [New Phase A progress](docs/role4/PROGRESS_REPORT_NEW_PHASE_A.md),
[verification](docs/role4/phase_a_verification.md),
[migration manifest](docs/role4/migration_manifest.md), and
[Phase B inputs](docs/role4/teammate_inputs.md).
