# Sensorimotor layer: setup, API and open items (Asvin)

Simulated world, sensors and actions. Imports only `contracts/`; never another layer.

## Run

```bash
python -m pytest tests/test_sensorimotor.py -q          # offline, no API key
python -m demo.app --scenario scenario_a                # terminal view; type `help`
python -m demo.app --scenario scenario_b --json         # full ToolResult JSON
```

## Use from code

```python
from sensorimotor import create_sensorimotor
sm = create_sensorimotor("scenario_a", seed=42)   # fresh, independent environment
sm.sensors.read_lidar()          # ToolResult envelope dict
sm.actions.move_forward(5)       # ToolResult envelope dict
sm.env.reset()                   # exact starting state again
registry = sm.tool_registry()    # {"read_lidar": fn, ...} for procedural's injected registry
```

Every tool returns a validated ToolResult envelope **dict** and never raises. Tools and
argument names follow Guidelines 4.5: `read_lidar(direction)`, `read_camera(target)`,
`get_position()`, `move_forward(distance_cm)`, `move_backward(distance_cm)`, `turn(degrees)`.
Error codes used: INVALID_ARGUMENT, NOT_FOUND, SENSOR_UNAVAILABLE, INTERNAL.

## World model

2-D plane in cm; +x is heading 0; positive turns are counter-clockwise. Obstacles are
rectangles that block movement and LiDAR. Objects are visual only (camera). Only actions
advance the simulated clock; reads do not. Noise is a pure function of (seed, sensor, step).
Scenario files live in `sensorimotor/scenarios/*.json`.

## Draft choices not stated in the Guidelines (confirm or change)

- A move cut short by an obstacle returns ok=true with the position reading's status `blocked`.
- Camera status: `clear` when an object is seen, `unknown` when none is.
- Scenario B: the box's true colour is `red`; yellow light shifts red to brown.
- LiDAR subject for the adapter: `path_A` / `status` (needs Vyom or Yash to confirm).

## Contracts

`sensorimotor/_boundary.py` is the only file that imports from Vyom's `contracts/` package.

