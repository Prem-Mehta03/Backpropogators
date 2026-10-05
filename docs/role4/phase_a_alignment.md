# New Phase A: team-plan alignment

As of 3 October 2026, the active workspace is `Backpropogators`, cloned from
`https://github.com/Prem-Mehta03/Backpropogators`. The old `I_Agent_Project` is the
preserved source and historical backup. No later scheduled phase is completed by
this migration.

## Layout and ownership

The published `docs/repository_structure.md` is authoritative. It describes more
modules than the checked-out repository contains. There is no AGENTS.md, separate
Team_Guidelines document, role document, shared `contracts/`, `declarative/`,
`sensorimotor/`, `adapters/`, `evaluation/`, `demo/`, pyproject.toml or .gitignore at
the baseline commit. Requirements and `.env.example` exist and are preserved.

Role 4 infrastructure sits in the planned top-level `evaluation/` namespace,
under `evaluation/role4/`. Tests remain under shared `tests/role4/`; offline demos
extend existing `scripts/`; documentation extends `docs/role4/`. This is a scoped
evaluation package, with no copied application root, nested README, dependencies,
virtual environment or historical report tree. Internal reference contracts and
logger avoid collisions with Vyom's shared contracts and `evaluation/logger.py`.
Production layers import neither these fixtures nor other layer internals.
Role 4 adapters call only public injected backend operations.

The existing Prem files are untouched. `tests/__init__.py` resolves the baseline
collision between `tests/procedural/` and production `procedural/` during pytest
discovery. `.gitignore` supplies the secret/cache/runtime exclusions described by
the team docs. README receives an additive Role 4 section; requirements stay intact.

## Source discrepancy and retained coverage

The requested historical baseline was 129 tests and old Phase 4 not started.
Measured source state has **169 passing tests**, a completed old Phase 4 README,
report, executable policies/backends and 40 additional tests. This evidence is
preserved. Only Phase 1–3 execution is migrated: 34 + 47 + 48 = **129 tests**.
Phase 4 hooks were removed from the shared runner, dispatcher, evaluator and
adapters; later implementations/tests/demos stay in the old project.

The registry still specifies all ten cases. Definitions are not runnable coverage.
S01 has stub/reference integration; S02/S03/S04/S05/S08 retain existing reference
execution, injected faults and human review worksheets. S04/S05 are preserved
regressions for Phase E. S06/S07/S09/S10 have no migrated execution policy or demo.
In particular, Prem's LiDAR proof is not an implementation of S07 (missing data).

## Accepted schedule

| Phase/date | Objective and current gap |
| --- | --- |
| A — 3 October | Repository setup, selective migration, measured baseline, alignment; review pending |
| B — next | Agree public APIs and integrate available teammate paths; reference missing layers |
| C — 4 October | S01/S02/S03/S07/S08, logs, mid-project build; S07 remains to be implemented |
| D — 5 October | Human reviews, test-results slide, report outline, rehearsal; pending |
| 6 October | Mid-project flash |
| 7–12 October | Midsem break |
| E — 13–18 October | S04/S05/S09, evidence hardening; S04/S05 retained, S09 pending |
| F — 19–25 October | S06/S10 and complete ten-case suite; pending |
| G — 26 October–1 November | Reliability, adversarial tests and demo; no hosted reliability trial yet |
| H — 2–4 November | Architecture report draft |
| 5–9 November | Diwali break |
| I — 10–12 November | Final verification and packaging |
| 13–14 November | Quiz break |
| 15 November | Submission |

Reviewed work on main and `v0.5-flash` are eventual October 4 targets. No main
publication or tag is authorized here. Historical reports and schedules do not
override this plan. Semantic review, production memory/sensors, procedural loop,
complete logging compatibility and hosted model reliability remain unverified.
