# Sensorimotor Layer: Technical Documentation

Role 2 | Owner: Asvin | Contract version 1.0 | Python 3.10 or newer

## 1. Purpose

The sensorimotor layer is the agent's body and world. It simulates a small environment, the sensors that observe it, and the actions that change it. It is the only source of live evidence in the system: what the robot measures right now. It reports measurements. It holds no beliefs and does no reasoning, which is what lets the other layers treat its output as evidence rather than as opinion.

The project separates the agent into three layers that meet only through tools and the shared JSON contracts:

| Layer | Responsibility | Owner |
| --- | --- | --- |
| Declarative | Stores beliefs with source, confidence, perspective and history; resolves conflicts | Vyom |
| Sensorimotor | Simulates the world, its sensors and its actions | Asvin |
| Procedural | Runs the LLM reasoning loop and calls the tools | Prem |

## 2. Design principles

- **Contract-only coupling.** The layer imports only the shared `contracts/` package, through a single boundary file. It never imports another layer.
- **No LLM logic.** Nothing in the environment calls a language model.
- **Deterministic.** The same scenario and seed always give the same readings. Noise is a pure function of (seed, sensor, step), and time comes from a simulated clock.
- **No global state.** Every run creates its own environment through a factory, so tests start clean.
- **Never raises.** Every tool returns a validated ToolResult envelope. Failures use the contract's fixed error codes.
- **Measurement is separate from belief.** Turning a reading into belief evidence happens in one place, the adapter, and the adapter never touches the belief store.

## 3. Components

| File | Responsibility |
| --- | --- |
| `sensorimotor/mock_env.py` | World state, geometry, simulated clock, reset, step, world changes |
| `sensorimotor/sensors.py` | LiDAR, camera and position sensors, and their tool functions |
| `sensorimotor/actions.py` | `move_forward`, `move_backward`, `turn` |
| `sensorimotor/config.py` | Loads and validates scenario JSON files |
| `sensorimotor/_boundary.py` | The only module that touches the contracts package |
| `sensorimotor/__init__.py` | Factory `create_sensorimotor()` and `tool_registry()` |
| `sensorimotor/stub.py` | Stateless fixture version of the API for other layers' tests |
| `sensorimotor/scenarios/` | Scenario A and Scenario B world files |
| `adapters/sensor_to_belief.py` | Converts a reading into belief evidence |
| `demo/app.py` | Terminal view of the world with an interactive prompt |
| `tests/test_sensorimotor.py` | 40 automated tests |

## 4. The simulated world

The world is a 2-D plane measured in centimetres. Heading 0 degrees points along the +x axis and positive turns are counter-clockwise. It contains:

- **Robot pose:** position and heading.
- **Obstacles:** axis-aligned rectangles that block both movement and LiDAR.
- **Objects:** a position and a true colour. They are visible to the camera only.
- **Lighting:** a colour-shift table that changes what the camera reports. Under yellow light, red is reported as brown.
- **Simulated clock:** starts at 2026-10-03T09:16:00Z. Each action advances one second. Reading a sensor does not advance time.

A reset restores the exact starting state. The world can also change during a run, either directly or through events scheduled in the scenario file (adding or removing an obstacle, changing the lighting, changing an object's colour).

## 5. Sensors

| Sensor | Measures | value | status | Confidence | Limits |
| --- | --- | --- | --- | --- | --- |
| LiDAR | Distance to the nearest obstacle along a direction | A number in cm | `blocked` at or below 30 cm, otherwise `clear` | 0.98 | One ray, 400 cm range; does not detect objects |
| Camera | The object in view and its apparent colour | `{object_id, color}` | `clear` if an object is seen, `unknown` if none | 0.9 | 60 degree field of view, 300 cm range, no occlusion |
| Position | The robot's pose | `{x, y, heading_deg}` | `clear`, or `blocked` if a move was cut short | 1.0 | None |

Any sensor can be switched off in the scenario file, in which case its tool returns SENSOR\_UNAVAILABLE. LiDAR can optionally add repeatable noise.

## 6. Actions

- `move_forward(distance_cm)` and `move_backward(distance_cm)`: distance must be greater than 0 and at most 500 cm. A move stops 1 cm short of an obstacle.
- `turn(degrees)`: the absolute value must be at most 360.

Each action returns the new pose as a position reading, so later sensor readings reflect what the robot has done.

## 7. Tool interface

| Tool | Arguments | Possible errors |
| --- | --- | --- |
| `read_lidar` | `direction` (front by default) | INVALID\_ARGUMENT, SENSOR\_UNAVAILABLE |
| `read_camera` | `target` (optional object\_id) | INVALID\_ARGUMENT, NOT\_FOUND, SENSOR\_UNAVAILABLE |
| `get_position` | none | SENSOR\_UNAVAILABLE |
| `move_forward`, `move_backward` | `distance_cm` | INVALID\_ARGUMENT, SENSOR\_UNAVAILABLE |
| `turn` | `degrees` | INVALID\_ARGUMENT, SENSOR\_UNAVAILABLE |

Every tool returns a ToolResult envelope, validated against the shared contract. An example from Scenario A:

```json
{"schema_version": "1.0", "tool": "read_lidar", "ok": true,
 "data": {"schema_version": "1.0", "sensor": "lidar_front", "value": 12, "unit": "cm",
          "status": "blocked", "timestamp": "2026-10-03T09:16:00Z", "confidence": 0.98},
 "error": null, "timestamp": "2026-10-03T09:16:00Z"}
```

To call the tools from code:

```python
from sensorimotor import create_sensorimotor

sm = create_sensorimotor("scenario_a", seed=42)   # fresh, independent environment
sm.sensors.read_lidar()                            # ToolResult envelope dict
sm.actions.move_forward(5)                         # ToolResult envelope dict
sm.env.reset()                                     # exact starting state again
registry = sm.tool_registry()                      # {"read_lidar": fn, ...} for the agent
```

An unexpected failure inside the layer is caught at the boundary and returned as an INTERNAL error envelope, so no exception ever crosses into another layer.

## 8. Scenarios

| Scenario | World | What the agent must handle |
| --- | --- | --- |
| Scenario A | The robot faces an obstacle 12 cm ahead | LiDAR reads 12 cm, blocked, which contradicts the stored map saying the path is clear |
| Scenario B | A box sits ahead under yellow light | The camera reports brown, while the user expects red and history says blue |

The map and history beliefs are seeded by the declarative layer. The sensorimotor layer supplies only the physical side of each scenario.

## 9. Sensor-to-belief adapter

The adapter is the one place where a sensor reading becomes belief evidence. It returns the arguments that `update_belief` expects: subject, predicate, object, source, confidence, perspective and reason.

| Reading | subject | predicate | object |
| --- | --- | --- | --- |
| LiDAR | `path_A` | `status` | The reading's status |
| Camera | The object id | `color` | The reported colour |

The source is the sensor name, the confidence is the reading's confidence, and the perspective is always `agent_sensor`. Readings with no usable evidence (unknown, error, nothing in view, position) produce no evidence at all. The adapter checks its own output against the belief field rules and never reads or writes the belief store.

## 10. Support for the ten evaluation tests

| Test | What the environment provides |
| --- | --- |
| 1 Map clear, LiDAR blocked | Scenario A |
| 2 Map blocked, LiDAR clear | A world with no obstacle ahead, built from a scenario file |
| 3 Three perspectives | Scenario B |
| 4 Very low sensor confidence | Per-sensor confidence set in the scenario file |
| 5 Two sensors disagree | Planned: second sensor (week 6) |
| 6 Stale historical belief | Clock control that ages the world without acting |
| 7 No belief or sensor data | Sensors that can be switched off |
| 8 False user information | Not driven by the environment |
| 9 Missing provenance | Not driven by the environment |
| 10 World changes during reasoning | Scheduled and direct mid-run world changes |

## 11. Testing and quality

The layer has 40 automated unit tests. They cover the Scenario A and B readings, the effect of actions on later readings, determinism and exact reset, mid-run world changes, every error path, validation of every output against the real contracts package, the tool registry, and the adapter. They run offline and need no API key.

```bash
conda activate i-agent
python -m pytest tests/test_sensorimotor.py -q
black --check -l 100 sensorimotor adapters demo tests/test_sensorimotor.py
ruff check sensorimotor adapters demo --line-length 100 --select E,F,I,B,UP
```

The terminal demo shows the world and accepts commands:

```bash
python -m demo.app --scenario scenario_a
```

## 12. Limitations and design decisions

- **Sensors report observations, not raw signals.** LiDAR returns one distance and the camera returns an identified object and colour. The contract defines these shapes. Perception is therefore folded into the sensor tool and the adapter, rather than left for the reasoning layer to deduce from raw data.
- **Simplified geometry.** LiDAR is a single zero-width ray. The camera tests only an object's centre point and has no occlusion. Objects do not block movement or LiDAR.
- **Defaults chosen where the Guidelines were silent.** Camera status is `clear` when an object is seen and `unknown` when none is. The LiDAR belief subject is `path_A` with predicate `status`. The blocked threshold is 30 cm. A move cut short by an obstacle returns success with position status `blocked`. All are set in one place and can be changed without touching the contract.
- **Stub behaviour.** The stub is a fixed fixture world with only a front LiDAR, so it rejects other directions with INVALID\_ARGUMENT. The real layer instead returns SENSOR\_UNAVAILABLE for a valid direction that has no sensor configured, which keeps a missing sensor distinct from a switched-off one.

## 13. Planned work

- **Week 6:** second sensor and a sensor-disagreement scenario, plus edge-case scenario configs.
- **Week 7:** refinements to the mid-run world-change hook and the time and staleness controls.
- **Week 8:** a richer demo view showing beliefs, tool calls and the final answer, which needs the other layers.

## 14. Reproducing the environment

```bash
git clone https://github.com/Prem-Mehta03/Backpropogators.git
cd Backpropogators
conda create -n i-agent python=3.11 -y
conda activate i-agent
pip install -r requirements.txt
python -m pytest tests/test_sensorimotor.py -q
```

Expected result: 40 passed.
