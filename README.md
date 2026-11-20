# Backpropogators

## Final Role 4 evaluation

Run the ten scenarios against the deterministic reference evaluator and against
the teammate stack with a scripted model in a simulated environment. Every
trial starts with fresh state. The runner saves per-case logs, traces and
separate pass rates for the reference and teammate paths. Explicit synthetic
fixtures and incomplete capabilities are marked in the results.

```powershell
python -B scripts/run_role4_offline_checks.py --suite full
python -B scripts/run_role4_final.py --trials 5 --seed 42
python -B scripts/run_role4_final.py --trials 1 --scenario S01 --scenario S03 --no-controls --show-cases
```

These commands use the existing Python dependencies in `requirements.txt`.
The suite can also use an existing compatible dependency directory via
`--dependency-path`. See the [final evaluation and submission instructions](docs/role4/final/README.md)
for the measured results, demo, evidence and outstanding team review items.

## Historical Role 4 evaluation foundation — New Phase A

Yash's Phase 1–3 evaluation infrastructure is scoped under `evaluation/role4/`,
with regression fixtures/tests in `tests/role4/` and three offline demo scripts.
It uses only Python's standard library (Python 3.10+). Shared `contracts/` and
Vyom's `evaluation/logger.py` remain owner-controlled; the scoped reference
ports/logger do not replace them. All demo layers are deterministic references.

From this repository root:

```powershell
python -B -S -m unittest tests.role4.test_evaluation -q
python -B -S scripts/run_role4_phase1_demo.py
python -B -S scripts/run_role4_phase2_demo.py
python -B -S scripts/run_role4_phase3_demo.py
# Available teammate client tests: uses installed pytest and injected fake APIs.
python -B -m pytest -p no:cacheprovider tests/procedural/test_llm_client.py -q
# For current full offline discovery, use scripts/run_role4_offline_checks.py.
```

Always exclude `live` tests for offline runs, even when a key is configured.
Demos write ignored reproducible outputs to `evaluation/logs/role4/phase1-3`.
Expected injected failures and malformed-payload rejections are demo successes;
they do not represent passing agent behavior. Human semantic review is pending.

See [New Phase A progress](docs/role4/PROGRESS_REPORT_NEW_PHASE_A.md),
[verification](docs/role4/phase_a_verification.md),
[migration manifest](docs/role4/migration_manifest.md), and
[Phase B inputs](docs/role4/teammate_inputs.md).

## Role 1 declarative layer

Vyom's v1.0 implementation is in `contracts/`, `declarative/`, and
`evaluation/logger.py`. It adds strict Pydantic boundary models, a NetworkX graph
view backed by SQLite provenance, evidence-priority handling, and JSON/JSONL
evaluation logging. Install dependencies from the repository root and run the
Role 1 tests with:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/test_contracts.py tests/test_declarative.py tests/test_evaluation_logger.py -q
```

The three-layer agent integration and Role 4 reference adapter still require
team review against the official v1.0 contracts. See
`docs/role1/integration_notes.md` for known interface differences.

Memory change events can be sent to Vyom's logger through the callback:

```python
from declarative import BeliefMemory
from evaluation.logger import EvaluationLogger

run_log = EvaluationLogger("evaluation/logs")
memory = BeliefMemory(
    event_callback=lambda event_type, details: run_log.log_event(
        "run_001", event_type, details
    )
)
```

The tool wrapper should use the same `log_event` method for the tool-call and
tool-result events, so the log can reconstruct the tool/state sequence.
