# Final Stretch Review Guide

This integration candidate combines the Role 4 evaluation branch and Prem's
procedural PR with the remaining contract, memory, simulator, and evaluation
work. The earlier Role 4 reference suite and its dated results remain a
record of the prior milestone. T01–T10 in `evaluation/runner.py` use the
newer requirements.

## Offline suite and playback

Use Python 3.10 or later with the repository requirements available. From
the repository root:

```powershell
python -B scripts/run_role4_offline_checks.py --suite full
python -B -m evaluation.runner --fake --repeats 3 --output-dir evaluation/logs/final/rehearsal
python -B -m evaluation.summarize --logs evaluation/logs/final/rehearsal --output-dir evaluation/logs/final/rehearsal-results
python -B -m evaluation.runner --fake --tests B_APPROACH --output-dir evaluation/logs/final/demo
```

On the review machine, both runner commands accept
`--dependency-path ../.venv/Lib/site-packages` to use the existing NetworkX
installation. Use the installed Miniconda Python binary if the Windows
`python` alias points to the Store shim. The offline test launcher explicitly
excludes the live agent test.

Each test directory has a Guidelines log and an `agent_run_*.json` trace.
The trace retains the model's requested tools, automatic calls, actual
envelopes and one frame per tool plus frame zero. To replay a saved trace:

```powershell
$trace = Get-ChildItem evaluation/logs/final/verified_20261123 -Recurse -Filter 'agent_run_*.json' |
    Where-Object { $_.Directory.Name -like 'T10__*' } | Select-Object -First 1
python -B scripts/live_ui.py --replay $trace.FullName --port 8765
```

Open `http://127.0.0.1:8765` after starting the server. For the four
demonstrations, choose an equivalent trace for T01, B_APPROACH, T05 and
T10. The saved trace drives the 3-D view without asking the model to rerun.
The viewer draws the deterministic 2-D simulation in 3-D. T10's first LiDAR
receipt is clear at 250 cm. The cart registers at 40 cm on the automatic
recheck. The raw reading remains clear by the 30 cm status threshold, while
the 100 cm movement is correctly refused by the distance plus 30 cm margin.

The captioned MP4 can be reproduced locally with `scripts/build_stretch_demo.py`,
using the four traces, the actual `evaluation/results/summary.json`, Pillow,
and Blender with H.264 support. See its `--help` for input and output paths.
Use the [narration outline](video_narration.md) for the team voice-over.

The review run passed 575 offline tests and 179 subtests with two pre-existing
collection warnings. The earlier reference demos and integration controls also
ran successfully. All four saved traces load through the replay parser, and
the browser viewer's JavaScript passes a syntax check. Interactive viewer
rendering remains to be checked on a browser. The captioned video was rendered
separately from the same frame data.

## Hosted evidence and release

Scripted results and hosted results are different measurement groups. The
recorded results table shows 3/3 scripted passes per test and zero recorded
comparable live trials. Once the team authorizes use of its own provisioned
keys, each owner can run their assigned cases against the same candidate:

```powershell
python -B -m evaluation.runner --live --tests T09,T10 --repeats 3 --output-dir evaluation/logs/final/yash-live
```

The live runner uses temperature 0, including retries, and logs the actual
model, whether it switched, and the answer source. Run the summarizer with
one `--logs` argument per evidence folder to combine distinct run IDs. Keep
keys in the existing ignored `.env` or environment, and confirm any trace
being shared contains only intended test data.

The handoff proposes Vyom for T01–T03, Asvin for T04–T06, Prem for T07–T08,
and Yash for T09–T10. The team needs to confirm the allocation before using
its API quotas.

The two memory writes are separate tool operations. Each has its own
transaction. The agent must disclose when just one succeeds. These
rehearsals cover a simulator and scripted model at fixed seed. They do not
measure hosted reliability.

For final submission, capture the cross-review decisions, verify the
remote main commit, and attach the real live results. The flash, release
candidate and final tags are team release decisions. The PDF marks the
release link pending until the team selects the reviewed commit.
