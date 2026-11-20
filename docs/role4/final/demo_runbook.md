# Final Evaluation Demo Runbook

Run these commands from the repository root with Python 3.10 or newer and the project's dependencies already available. The commands use an injected scripted model and simulated environments. The full test discovery explicitly excludes live-model tests. On the measured Windows machine, use `C:/Users/Yash/miniconda3/python.exe` if `python` resolves to a shim, and add `--dependency-path ../.venv/Lib/site-packages` to both evaluation runners to resolve the existing pure-Python NetworkX package. Each run needs a fresh output directory.

```powershell
python -B scripts/run_role4_offline_checks.py --suite full
python -B scripts/run_role4_final.py --trials 5 --seed 42 --output-dir evaluation/logs/role4/final_20261120_verified
```

Read `summary.json` and `metrics.csv` first, then open the individual `run.json` and trace files. The regular runner verifies that the evidence records agree and records the observed behavior failures. `--strict` returns a failing status if the canonical behavior checks fail. An evidence run can be valid while a behavior check fails.

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
3. **Failure evidence.** Open `S01_unsupported_update/run.json` and `S08_movement_attempt/run.json`. Show the actual incorrect write and the attempted, dispatched and executed movement. Explain that evaluation catches both problems.
4. **Results.** Show per-case metrics and the evidence for a passing check. Distinguish genuine layer execution from synthetic fixture inputs, simulated worlds and scripted output. State that team review and hosted-model trials remain pending.

The quick playback supports `--dependency-path ../.venv/Lib/site-packages` on the same Windows setup. If a live rehearsal machine is unavailable, show the verified packaged traces for these cases. The earlier [mid-project speaking script](../phase_d/speaking_script.md) and [slide content](../phase_d/slide_content_and_notes.md) are available for the historical flash presentation.

## Build the local submission package

The packaging script takes tracked repository files and the explicit final contribution manifest. One fresh, explicitly chosen run supplies JSON, JSONL and CSV evidence. The ZIP stores those files under `evidence/` and includes sizes and SHA-256 hashes under `MANIFEST.json`. The package uses a stable entry order and fixed timestamps. The build refuses to overwrite an existing archive.

```powershell
python -B scripts/package_role4_final.py --evidence evaluation/logs/role4/final_20261120_verified --include-from docs/role4/final/contribution_files.txt --output evaluation/logs/role4/role4_final.zip
python -B scripts/package_role4_final.py --verify evaluation/logs/role4/role4_final.zip
```

Before sharing a ZIP, inspect the evidence and compare the claims to the actual rehearsal. Use the [review packet](review_packet.md) to record team decisions before publication. The team plan names `v0.5-flash` and `v1.0-final` as release tags. Create either tag only after identifying the corresponding reviewed commit and receiving the team release decision.
