# Sensorimotor world schema (draft v1, Asvin)

The world is described by one JSON file per scenario in `sensorimotor/scenarios/`.
Loaded and validated by `sensorimotor/config.py`. Distances in cm, angles in degrees,
timestamps ISO 8601 UTC with a trailing Z. This is internal to the sensorimotor layer;
nothing here crosses a layer boundary except through the contract JSON that the sensors
and actions return.

## Top level

| Field | Type | Default | Meaning |
|---|---|---|---|
| name | string | required | Scenario id, for example `scenario_a` |
| description | string | "" | Free text |
| seed | integer | 0 | Same seed + scenario = same readings |
| start_time | timestamp | 2026-10-03T09:00:00Z | Simulated clock at reset |
| tick_seconds | number | 1 | Clock advance per action |
| collision_margin_cm | number | 1 | Gap kept from an obstacle when a move is cut short |
| max_move_cm | number | 500 | Largest allowed single move |

## World state

| Field | Shape | Meaning |
|---|---|---|
| robot | `{x, y, heading_deg}` | Pose. Heading 0 = +x; positive turns are counter-clockwise |
| obstacles | list of `{obstacle_id, x_min, y_min, x_max, y_max}` | Rectangles; block movement and LiDAR |
| objects | list of `{object_id, x, y, true_color}` | Visible to the camera only |
| lighting | `{name, color_shift}` | `color_shift` maps true colour to the colour the camera reports (yellow light: red to brown) |
| events | list of `{at_step, change}` | World changes applied when the step counter reaches `at_step` (test 10 hook) |

`change.type` is one of `add_obstacle`, `remove_obstacle`, `set_lighting`, `set_object_color`.

## Sensors

| Sensor | Fields (defaults) |
|---|---|
| lidar (list) | `name`, `direction` (front, back, left, right), `max_range_cm` (400), `blocked_threshold_cm` (30), `confidence` (0.98), `noise_std_cm` (0), `available` (true) |
| camera | `name` (camera_front), `fov_deg` (60), `max_range_cm` (300), `confidence` (0.9), `available` (true) |
| position | `name` (position), `confidence` (1.0), `available` (true) |

`available: false` makes the tool return `SENSOR_UNAVAILABLE`.

## Sensor output (contract, Guidelines 4.3)

| Sensor | value | unit | status |
|---|---|---|---|
| LiDAR | distance as a number | cm | `blocked` if value <= `blocked_threshold_cm`, else `clear` |
| camera | `{object_id, color}` | null | `clear` if an object is seen, `unknown` if none (draft choice) |
| position | `{x, y, heading_deg}` | null | `clear`, or `blocked` when a move was cut short (draft choice) |
