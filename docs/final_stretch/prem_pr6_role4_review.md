# Role 4 follow-up for Prem’s draft PR #6

Reviewed `feature/prem-live-fixes` at `260de848c20ced809e493afa9eef45d9a190a08c`. Prem requested that Role 4 review the S08 cancellation, the scripted history plans and the route-clear wording check on the replacement draft. [Prem’s comment](https://github.com/Prem-Mehta03/Backpropogators/pull/4#issuecomment-7144665258) · [Draft PR #6](https://github.com/Prem-Mehta03/Backpropogators/pull/6)

- **S08 movement control.** The script asks for a 20 cm move and sees an automatic LiDAR recheck reject it. The evaluator requires unchanged simulated pose and a completed scripted answer that reports cancellation. The answer comes from the rejected move receipt. Before this follow-up, the guard could cancel the move while the script reached its step limit because it omitted history.
- **History plans and T06 evidence.** Route scripts consult `path_A/status` history before relying on it. The default checklist requires matching history for each queried route. A storage failure or a history call about another subject or predicate leaves the requirement open. T06 verifies that the agent saw the linked September map and active revised plan in the same receipt. The scripted answer uses that receipt and abstains if the pair is missing.
- **T04 and T05 wording.** The evaluator and procedural guard share a clause-aware check. It accepts “I cannot confirm whether the route is clear” and source-attributed statements. An independent clearance claim in a later sentence or contrast clause is still flagged. This is a wording regression check for the covered patterns.

## Offline verification

- Full pytest suite passed 675 tests and 179 subtests. The two collection warnings came from the imported `TestRunRecord` dataclass. The offline guard recorded zero network attempts.
- Formal T01–T10 acceptance passed 30/30 scripted runs with zero fallbacks. All 30 traces replayed successfully and used the actual teammate tools.
- The Role 4 suite passed 45/45 exercised canonical behavior runs and 15/15 canonical controls. Five S07 temperature runs remained scoped diagnostics, so the strict gate returned 2. The S08 control logged a 12 cm automatic LiDAR read, a rejected dispatch, unchanged pose and a completed cancellation answer. The S10 control’s trace and logger records also replayed successfully.
- The audit parsed 718 JSON and JSONL artifacts from the fresh offline runs.

## Separate movement issue for Prem and Asvin

The draft’s range exception can accept a long move when ultrasonic returns its 200 cm limit and LiDAR cannot see glass. In the simulated T05 world with glass at 215–218 cm, a 230 cm request passed the recheck with 400 cm LiDAR and 200 cm ultrasonic. The action then travelled 214 cm before reporting blocked. The 200 cm reading only covers distance within the ultrasonic sensor’s range. Prem and Asvin should review requiring clearance across the whole requested distance plus margin or splitting long moves into shorter, separately rechecked moves. [Draft recheck implementation](https://github.com/Prem-Mehta03/Backpropogators/blob/260de848c20ced809e493afa9eef45d9a190a08c/procedural/recheck.py#L116) · [Simulator distance sensors](https://github.com/Prem-Mehta03/Backpropogators/blob/260de848c20ced809e493afa9eef45d9a190a08c/sensorimotor/sensors.py#L59)

```python
import json
from pathlib import Path

from procedural.recheck import recheck_before_action
from sensorimotor import create_sensorimotor

path = Path("sensorimotor/scenarios/scenario_t05_sensor_disagreement.json")
config = json.loads(path.read_text(encoding="utf-8"))
config["obstacles"][0].update(x_min=215, x_max=218)
config["sensors"]["lidar"][0]["max_range_cm"] = 400
tools = create_sensorimotor(config).tool_registry()
recheck = recheck_before_action("move_forward", {"distance_cm": 230}, tools)
print(recheck.details["passed"], [r["result"]["data"]["value"] for r in recheck.details["reads"]])
if recheck.cancel is None:
    print(tools["move_forward"](230)["data"])
```

## Reproduce offline

Run from the repository root using Python with the existing project dependencies available.

```powershell
python -B scripts/run_role4_offline_checks.py --suite full
python -B -m evaluation.runner --fake --repeats 3 --output-dir evaluation/logs/role4/pr6/t_suite
python -B -m evaluation.summarize --logs evaluation/logs/role4/pr6/t_suite --output-dir evaluation/logs/role4/pr6/t_summary
python -B scripts/run_role4_final.py --trials 5 --seed 42 --strict --output-dir evaluation/logs/role4/pr6/s_suite
```

The official T cases and Role 4 S cases use scripted model replies and simulated environments. The full offline harness excludes the live-agent module and the hosted single-tool test. Hosted T04/T05/T06 reruns and human review remain pending. The strict Role 4 gate counts the unsupported S07 temperature capability as pending.
