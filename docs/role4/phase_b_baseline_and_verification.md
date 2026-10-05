# New Phase B baseline and verification

Active clone: `C:\Users\Yash\OneDrive\Documents\Study\AI\Backpropogators`.
Branch: `feature/yash-evaluation-foundation`. Base remains
`14fcd6a4804e90f57d42b5dab7d4c40ff7600c8c`; origin is the canonical
`https://github.com/Prem-Mehta03/Backpropogators.git`. Existing Phase A changes
were preserved. No AGENTS.md is present; the published repository structure and
procedural setup docs were read. No separate Team_Guidelines or pyproject is present.

## Measured baseline before edits

| Check | Result |
| --- | --- |
| Clone Role 4 unittest discovery | 129 passed, 1.631 seconds |
| Existing teammate client pytest | 10 passed, 0.03 seconds |
| Combined available pytest | 139 passed, two non-test dataclass collection warnings, 136 subtests |
| Full offline discovery with continuation | 139 passed **and two collection errors**; full suite blocked |
| Migrated Phase 1, 2, 3 demos | All exit 0; expected valid/fault/contract-error outcomes |

The Phase A record of 169 source tests, including 40 historical Phase 4 tests,
was verified against its manifest, reports, code and test inventory. The historical
suite was not rerun or edited in Phase B; it is not a newly measured Phase B result.
The historical source's 155 files are checked for preservation at the end.

## Verification after edits

| Check | Result |
| --- | --- |
| All Role 4 tests | **144 passed**, 1.480 seconds: original 129 plus 15 focused Phase B tests |
| Existing teammate client tests | **10 passed**, 0.02 seconds; untouched |
| Combined available suites | **154 passed**, two warnings, 143 subtests |
| Full offline discovery | **154 passed and two collection errors**; not a full-suite pass |
| New focused compatibility/harness tests | **15 passed**: seven harness, eight client tests |
| Existing Phase 1–3 demos | All exit 0; original check counts and intended fault detections preserved |
| Client compatibility smoke | Four expected outcomes verified with real Prem client code and fake API |

No tests were skipped to conceal errors. Seven tool-wrapper and five offline
single-tool tests cannot collect because official modules are missing. One live
test is deliberately excluded by `-k 'not live'`, but its containing module also
cannot collect: it is not counted as a measured pytest skip. Hosted trials,
three-layer teammate integration and human semantic review remain unavailable.
Installed pytest/pydantic/dotenv suffice for available checks. openai/black/ruff
are absent; no installation or formatter run occurred. The absent openai package
is not the cause of these collection errors and is not needed by injected clients.

## Reproduction from the clone

```powershell
..\.venv\Scripts\python.exe -B -S -m unittest discover -s tests/role4 -q
python -B -m pytest -p no:cacheprovider tests/procedural/test_llm_client.py -q
python -B -m pytest -p no:cacheprovider tests/role4 tests/procedural/test_llm_client.py -q
# Exclude live calls even if keys exist; continuation exposes available tests and blockers.
python -B -m pytest -p no:cacheprovider tests -k 'not live' --continue-on-collection-errors -q
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase1_demo.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase2_demo.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase3_demo.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase_b_smoke.py
```

The smoke writes ignored `evaluation/logs/role4/phase_b/prem_client_trace.jsonl`
and `prem_client_result.json`. Small current snapshots are saved under
[phase_b_evidence](phase_b_evidence/README.md). Error log lines from injected
timeouts and malformed JSON are expected controlled outcomes, not hidden failures.
Client events distinguish requests, normalised responses and propagated errors;
parsed tool requests are not executed sensor returns and create no evidence.

Reference harness checks verify repeatable reset/reuse of all layers, public
initial/final snapshots, paired observed calls/returns, unique evidence IDs,
contract-error aborts, empty-query status, explicit non-execution of rejected
movement, and continued rejection of deferred scenario entry points. Existing
tests preserve the distinction between correct metadata and unreviewed prose.
The new receipt flags strengthen existing trace_integrity without changing demo
check counts or relaxing contracts.

[Baseline output](phase_b_baseline.json) preserves measured pre-edit output.
[Final audit](phase_b_verification.json) records final commands, clone import
origins, reproducibility/artifact parsing, preservation, pending reviews and
content checks. [Phase B file list](phase_b_files.txt) is incremental; the Phase A
proposed file list remains a historical snapshot, not the complete current scope.
