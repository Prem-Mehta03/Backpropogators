# Selective migration manifest

Every one of the 155 source files is classified in
[migration_manifest.json](migration_manifest.json), with source/destination paths,
decision, rationale, original source hash and destination hash where applicable.
The original hash precedes baseline tests; those tests may regenerate artifacts.

- **ADAPT: 28 files**
- **ALREADY PRESENT / equivalent: 1 files**
- **COPY unchanged: 9 files**
- **DEFER: 7 files**
- **KEEP historical: 110 files**

37 source files form the coherent Phase 1-3 package, fixtures, regression tests,
three demos and four adapted reference guides. Internal ports/logger are scoped
under evaluation/role4 to protect Vyom ownership. Tests and scripts extend the
existing team directories rather than replacing them. Source reports and bulk
artifacts are retained only in the historical source. Later execution policies,
backends, checks, test_phase4 and run_phase4_demo are deferred; residual shared
Phase 4 execution hooks were stripped from migrated files.

No unresolved content collision was overwritten. No source file is deleted.
Shared-schema/API disagreements require team review in Phase B; they remain
documented gaps rather than fake top-level contracts or manufactured passes.
New README section, package markers, ignore rules, audit documents and current
clone-generated representative evidence are additions, not source copies.
See proposed_commit_files.txt for the exact eventual commit scope.
