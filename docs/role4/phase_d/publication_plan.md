# Proposed publication plan and separate release gates

**Preparation only. No staging, commit, push, PR or release action executed.**

Proposed commit message: `Prepare Role 4 reference evaluation and mid-project review contribution`

Proposed PR title: `Add Role 4 reference evaluation and mid-project review preparation`

The exact body is `pr_body.md`. It describes cumulative A–D scope, the 177
available Phase C passes, unsuccessful full discovery, reference/fake-API labels,
rehearsal validation and remaining human/integration gates. It does not claim that
October 5 peer review or October 6 presentation occurred.

## Proposed contribution scope

Use `../proposed_commit_files_phase_d_cumulative.txt` as the current exact list.
The Phase C 85-file list remains an unchanged historical snapshot. The new list
contains the scoped A–C foundation/evidence plus the Phase D deck, editable source,
notes/script/questions, review and assembly preparation, runbook, unsent owner
decisions, small evidence/rehearsal/verification summaries and publication text.

Include the small A–C evidence already proposed and Phase D `evidence_summary.json`
and `rehearsal_record.json`. They distinguish test methods, scenario executions,
backend/model mode, capture provenance and failure reasons. Full generated logs,
deck drafts, render PNGs, caches and runtimes stay under ignored `evaluation/logs/`.
Another person regenerates them with the runbook commands. Do not force-add all
runtime outputs or add `.env`, virtual environments or teammate placeholders.

## Safe future commands, only after explicit publication authorization

Before running anything below, re-read the actual list and working diff. Verify
HEAD/branch and remote. The local base is older than fetched origin/main; do not
merge/rebase the dirty contribution automatically. A later base change requires
a separate approved plan and owner tests, as documented in the Phase C gap report.

```powershell
Set-Location 'C:\Users\Yash\OneDrive\Documents\Study\AI\Backpropogators'
$gitOptions = @('-c', 'safe.directory=C:/Users/Yash/OneDrive/Documents/Study/AI/Backpropogators')
git @gitOptions branch --show-current
git @gitOptions status --short
git @gitOptions remote -v
if ((git @gitOptions branch --show-current) -ne 'feature/yash-evaluation-foundation') { throw 'Unexpected branch' }
if ((git @gitOptions rev-parse HEAD) -ne '14fcd6a4804e90f57d42b5dab7d4c40ff7600c8c') { throw 'Base changed: review a new publication plan' }
if ((git @gitOptions diff --cached --name-only)) { throw 'Existing staged changes: inspect before proceeding' }
$paths = Get-Content docs/role4/proposed_commit_files_phase_d_cumulative.txt
foreach ($path in $paths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing proposed file: $path" }
    if ($path -match '(^|/)(\.git|\.venv|__pycache__|\.pytest_cache|node_modules)(/|$)|^evaluation/logs/|(^|/)\.env$') { throw "Excluded path: $path" }
}
foreach ($path in $paths) {
    git @gitOptions add -- $path
    if ($LASTEXITCODE -ne 0) { throw "Staging failed: $path" }
}
git @gitOptions diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged whitespace check failed' }
git @gitOptions diff --cached --stat
$staged = @(git @gitOptions diff --cached --name-only)
if (Compare-Object ($paths | Sort-Object) ($staged | Sort-Object)) { throw 'Staged scope differs from the approved list' }
git @gitOptions diff --cached
# Pause here for actual staged-content review and compare staged paths with the exact list.
git @gitOptions commit -F docs/role4/phase_d/proposed_commit_message.txt
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git @gitOptions push -u origin feature/yash-evaluation-foundation
if ($LASTEXITCODE -ne 0) { throw 'Push failed' }
gh pr create --draft --base main --head feature/yash-evaluation-foundation --title 'Add Role 4 reference evaluation and mid-project review preparation' --body-file docs/role4/phase_d/pr_body.md
```

Commands require valid Git/GitHub tooling and authentication, which this phase
does not establish. Stop on failure, never force-push. If a PR is later created,
attach it to the Codex chat and obtain actual peer review. The author does not
merge their own PR under the repository convention. These text examples authorize
no current publication or external review request.

## Contribution publication checklist

- [ ] Yash reviews the deck, report, exact list and honest blockers.
- [ ] User explicitly authorizes staging/commit/push/draft PR.
- [ ] Branch, base, remote and staged scope are checked again.
- [ ] Included snapshots and local reproduction instructions remain accurate.
- [ ] Actual PR peer review occurs and any owner feedback is addressed.

## Full v0.5-flash team gate, independent of publication

- [x] Five-case reference evaluation and intended fault detection.
- [ ] Approved contracts, memory/logger, sensors/environment and complete agent APIs.
- [ ] Actual three-layer integration with honest backend/model labels.
- [ ] Full offline discovery with no unresolved collection errors.
- [ ] Exact Scenario A/B fixture agreement, including named provenance/lighting if required.
- [ ] Actual human prose review and peer review.
- [ ] Authorized team merge to main by the appropriate reviewer.
- [ ] Authorized release decision and tag.

Real-model reliability remains unmeasured and requires future trials. No publication
or tag command is proposed as a substitute for missing team gates.
