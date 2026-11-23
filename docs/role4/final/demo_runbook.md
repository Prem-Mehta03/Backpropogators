# Role 4 Regression and Demo Runbook

For the current T01–T10 acceptance suite and recorded 3-D playback, see the [final stretch guide](../../final_stretch/README.md). The commands here exercise the original S01–S10 scenarios and support replaying the older Role 4 handoff.

Run from the repository root in a Python 3.10+ project environment with `requirements.txt` available. Use the interpreter that can import the project's dependencies, such as `python` in the activated virtual environment. The offline launcher excludes the live-model tests and guards against network calls. Choose a fresh output directory.

```sh
python -B scripts/run_role4_offline_checks.py --suite full
python -B scripts/run_role4_final.py --trials 5 --seed 42 --output-dir evaluation/logs/role4/regression_rehearsal
```

On Windows, if `python` resolves to the Store shim, use the full path to your virtual environment's `Scripts/python.exe`. For an existing split dependency setup, both runners also accept `--dependency-path <compatible-site-packages>`.

Read `summary.json` and `metrics.csv` first, then open the individual `run.json` and trace files. The runner verifies that the evidence agrees with the observed outcomes. `--strict` also flags canonical behavior gaps and unsupported capability scopes. Keep the diagnostic S07 temperature probe separate from scored behavior.

## Scenario A and B walkthrough

For a quick terminal walkthrough of both worlds, select the two normal cases and print their before/after evidence.

```powershell
python -B scripts/run_role4_final.py --trials 1 --scenario S01 --scenario S03 --no-controls --show-cases --output-dir evaluation/logs/role4/final_demo_ab
```

Use the published teammate-code runner to reproduce the two original controls and inspect the raw case objects.

```powershell
$demo = 'evaluation/logs/role4/final_demo_controls'
python -B scripts/run_role4_teammate_integration.py --controls --output-dir $demo
$a = Get-Content -Raw -LiteralPath "$demo/S01_valid/run.json" | ConvertFrom-Json
$b = Get-Content -Raw -LiteralPath "$demo/S03_valid/run.json" | ConvertFrom-Json
foreach ($case in @($a, $b)) {
    $case.agent.question
    $case.state_before.memory.nodes | Select-Object belief_id,perspective,object,source,status
    $case.agent.tool_calls | ConvertTo-Json -Depth 12
    $case.state_after.memory.nodes | Select-Object belief_id,perspective,object,source,status,valid_to,supersedes
    $case.agent.answer
    $case.evaluation | ConvertTo-Json -Depth 12
}
```

1. **Scenario A.** Show the historical clear map entry and the 12 cm blocked LiDAR result. Explain the successor belief and show that the prior map is still available in history.
2. **Scenario B.** Show the red user statement, blue `bot_02` fixture claim, and camera observation of brown under yellow lighting. Compare the sources and perspectives before reading the scripted answer.
3. **Safety regressions.** Open `S01_unsupported_update/run.json` and `S08_movement_attempt/run.json`. On the final stretch, the first checks that the contradictory write is refused. The second checks that an automatic read cancels the requested move before dispatch. The original 20 November runs show the prior failures, including 11 cm of simulated movement.
4. **Results.** Show per-case metrics and the evidence for a passing check. Distinguish genuine layer execution from synthetic fixture inputs, simulated worlds and scripted output. State that team review and hosted-model trials remain pending.

If a rehearsal machine is unavailable, show the recorded traces for the relevant commit. The earlier [mid-project speaking script](../phase_d/speaking_script.md) and [slide content](../phase_d/slide_content_and_notes.md) are available for the historical flash presentation.

## Rebuild the earlier local package

Use the original PR #3 checkout if you need to reproduce the 20 November source and evidence package. The packaging script takes the checked-out tracked files and the explicit contribution manifest. One chosen run supplies JSON, JSONL and CSV evidence. The ZIP stores those files under `evidence/` with sizes and SHA-256 hashes under `MANIFEST.json`. The build refuses to overwrite an existing archive.

```powershell
python -B scripts/package_role4_final.py --evidence evaluation/logs/role4/final_20261120_verified --include-from docs/role4/final/contribution_files.txt --output evaluation/logs/role4/role4_final.zip
python -B scripts/package_role4_final.py --verify evaluation/logs/role4/role4_final.zip
```

Before sharing a ZIP, inspect the evidence and compare the claims to the actual rehearsal. Use the [review packet](review_packet.md) to record team decisions before publication. The team plan names `v0.5-flash` and `v1.0-final` as release tags. Create either tag only after identifying the corresponding reviewed commit and receiving the team release decision.
