# New Phase A baseline and verification

Measured 3 October 2026, Windows PowerShell, repository base
`14fcd6a4804e90f57d42b5dab7d4c40ff7600c8c`, local branch
`feature/yash-evaluation-foundation`. Origin fetch/push URL is exactly
`https://github.com/Prem-Mehta03/Backpropogators.git`. Destination was absent; it
was cloned, initially clean on main tracking origin/main. The team branch naming
pattern `feature/prem-<short-name>` was applied to Yash. No publication occurred.

## Baselines before migration

| Check | Measured result |
| --- | --- |
| Old source unittest discovery | 169 passed in 2.168 seconds; 40 are historical Phase 4 tests |
| Unrelated Lab5 Bayesian Networks | 7 passed in 0.003 seconds; not migrated |
| Original Phase 1–3 demos | Exit 0 for each; expected valid/fault/contract-error outcomes |
| Team full offline pytest | Initial tests/procedural package collision plus missing contracts; importing production client first exposes two missing-contract collection errors |
| Team client tests with production import first | 10 passed in 0.02 seconds using injected fake APIs |

The reported 129-test baseline and 'old Phase 4 not started' conflict with disk
evidence. Source README/reports/code remain intact; tests regenerated artifacts.

## Post-migration verification

From the clone, using existing parent `.venv\Scripts\python.exe` for standard
library checks and existing miniconda Python for pytest:

```powershell
..\.venv\Scripts\python.exe -B -S -m unittest discover -s tests/role4 -q
python -B -m pytest -p no:cacheprovider tests/role4 tests/procedural/test_llm_client.py -q
python -B -m pytest -p no:cacheprovider tests -k 'not live' -q
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase1_demo.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase2_demo.py
..\.venv\Scripts\python.exe -B -S scripts/run_role4_phase3_demo.py
```

- Role 4: **129 passed** (34 + 47 + 48). No assertions removed, tests renamed or
  skips added. Import, registry, artifact and script paths were adapted.
- Combined available suites: **139 passed**, plus 136 unittest subtests;
  two pytest warnings refer to imported TestRunRecord dataclasses, not missing tests.
- Full offline discovery: **two collection errors**, in pre-existing
  test_single_tool_call.py and test_tools.py because `contracts.models` is absent.
  `sensorimotor.stub` is another known missing import once contracts are supplied.
  Full suite is **blocked**, not reported passing. The tests package marker fixes
  the original production/test procedural name collision.
- Only one live test exists in the checked-out suite; `-k 'not live'` excludes it
  independently of configured keys. No hosted scripts, API calls or LLM trial ran.
- Phase 1: valid 20/20, injected invalid 11/20; nine expected failures.
- Phase 2: PASS 20/20, injected FAIL 11/20, malformed sensor CONTRACT ERROR with
  evaluated=false; all expected outcomes verified.
- Phase 3: S02 34/34 vs 30/34, S03 38/38 vs 32/38, S04 36/36 vs 26/36,
  S05 40/40 vs 29/40, S08 35/35 vs 27/35; all intended fault checks detected.

Default miniconda has pytest, pydantic and dotenv; openai, black and ruff are
absent. Parent existing .venv has none of those packages. No package installation
or environment creation occurred. Hosted tools are unavailable and untested;
formatters were not run. No fake dependencies were manufactured.

The machine-readable [verification record](phase_a_verification.json) records
final discovery counts, clone import paths, artifact parsing, preservation hashes,
secret/runtime audit and repository status. [Representative evidence](evidence/README.md)
is generated from this clone, not copied old verification. Other outputs are
ignored and reproducible. Every measured demo uses reference layers; Phase 1 is
a scripted fixture, Phases 2–3 deterministic reference policies. The 10 client
tests execute real Prem client code with a fake API. No real/mixed integrated
demo or hosted reliability result is claimed. Human semantic review is pending.
