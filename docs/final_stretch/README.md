# Final Stretch Review Guide

This integration candidate combines the Role 4 evaluation branch and Prem's
procedural PR with the remaining contract, memory, simulator, and evaluation
work. The earlier Role 4 reference suite and its dated results remain a
record of the prior milestone. T01–T10 in `evaluation/runner.py` use the
newer requirements.

The 23 November capture is pinned to `04d6f63`. It measured 575 offline
tests and 179 subtests, and its T01–T10 results were 30/30 scripted passes
with zero fallback answers. The 405-test count and 45/50 raw verdicts in
PR #3 refer to the 20 November baseline. That raw total includes five
unsupported-temperature diagnostics. The corresponding behavior score was
40/50 planned cases and 40/45 eligible attempts. See [the review follow-up](prem_pr4_review.md)
and [the measurement breakdown](../role4/final/README.md).

- [Pinned acceptance results](https://github.com/Prem-Mehta03/Backpropogators/blob/04d6f63c4ee17bcdf870fff302721e91ef9c0218/evaluation/results/results_table.md)
- [Pinned individual logs and replay traces](https://github.com/Prem-Mehta03/Backpropogators/tree/04d6f63c4ee17bcdf870fff302721e91ef9c0218/evaluation/logs/final/verified_20261123)
- [PDF report build instructions](report_source.md)

## Offline suite and playback

Use Python 3.10 or later in a project environment with the repository
requirements available. From the repository root:

```sh
python -B scripts/run_role4_offline_checks.py --suite full
python -B -m evaluation.runner --fake --repeats 3 --output-dir evaluation/logs/final/rehearsal
python -B -m evaluation.summarize --logs evaluation/logs/final/rehearsal --output-dir evaluation/logs/final/rehearsal-results
python -B -m evaluation.runner --fake --tests B_APPROACH --output-dir evaluation/logs/final/demo
```

Use `python` from your activated project environment. On Windows, if that
command opens the Store, use the environment's `Scripts/python.exe` directly.
An existing split dependency setup can use `--dependency-path <site-packages>`.
The offline test launcher excludes the live agent test and guards against
network calls.

Each test directory has a Guidelines log and an `agent_run_*.json` trace.
The trace retains the model's requested tools, automatic calls, actual
envelopes and one frame per tool plus frame zero. To replay the pinned T10 trace:

```sh
python -B scripts/live_ui.py --replay evaluation/logs/final/verified_20261123/T10__20261123T052100961327Z-01/agent_run_20261123T052100961327Z-01.json --port 8765
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

The captured run had two pre-existing collection warnings. The earlier
reference demos and integration controls also ran successfully. All four
saved traces load through the replay parser, and
the browser viewer's JavaScript passes a syntax check. Interactive viewer
rendering remains to be checked on a browser. The captioned video was rendered
separately from the same frame data.

## Fixture choices

The release-facing Scenario A is T01. It loads `default_map` at 1.00, records
the 12 cm blocked observation, then explicitly downgrades and updates. The
pinned trace shows the 1.00 map retained in history, its 0.30 successor retained
in history, and an active 0.98 `lidar_front` belief linking back to that successor.
[T01 trace](https://github.com/Prem-Mehta03/Backpropogators/blob/04d6f63c4ee17bcdf870fff302721e91ef9c0218/evaluation/logs/final/verified_20261123/T01__20261123T052100961327Z-01/agent_run_20261123T052100961327Z-01.json)

The canonical S01 regression uses the same seed and tool sequence. Its
reference counterpart preserves the earlier fixture for comparison.

Scenario B uses `box_01` and keeps these values in separate active beliefs:

| Value | Source | Perspective | Confidence |
| --- | --- | --- | ---: |
| red | `user` | `user` | 0.90 |
| blue | `bot_02` | `third_party` | 0.80 |
| brown | `camera_front` | `agent_sensor` | 0.90 |

The camera value is the apparent color produced by the yellow-light simulator
fixture. The third-party report stays attributed to its source. The separately
recorded B-approach demo adds movement and a second camera read.
[T03 trace](https://github.com/Prem-Mehta03/Backpropogators/blob/04d6f63c4ee17bcdf870fff302721e91ef9c0218/evaluation/logs/final/verified_20261123/T03__20261123T052100961327Z-01/agent_run_20261123T052100961327Z-01.json)

## Hosted evidence and release

Scripted results and hosted results are different measurement groups. The
recorded results table shows 3/3 scripted passes per test and zero recorded
comparable live trials. The review environment has no configured hosted
model credentials or compatible OpenAI SDK. With those dependencies in
place, each authorized owner can run their assigned cases against the same
candidate:

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
rehearsals measure the simulator and scripted model at a fixed seed.

The PDF sections are drafts for Prem, Vyom and Asvin to check against their
layer code and the published traces. Their approval, team cross-review,
hosted evidence and release tags are pending. Record those decisions before
linking a tagged release in the PDF. See the [review checklist](../role4/final/review_packet.md).
