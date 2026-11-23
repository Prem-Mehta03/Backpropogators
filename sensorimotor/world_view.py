"""Export read-only frames for the demo. The renderer never measures the world."""

from __future__ import annotations

from typing import Any

from .mock_env import MockEnvironment

FLOOR_MARGIN_CM = 100
ROBOT_RADIUS_CM = 20
OBJECT_SIZE_CM = 30


def export_frame(env: MockEnvironment) -> dict[str, Any]:
    """Copy the scene and last actual sensor receipts without advancing time."""
    state = env.get_state()
    additions = env.obstacle_additions
    obstacles = []
    for item in state["obstacles"]:
        obstacle = {k: v for k, v in item.items() if k != "obstacle_id"}
        obstacle.update(id=item["obstacle_id"], added_at_step=additions.get(item["obstacle_id"]))
        obstacles.append(obstacle)
    robot = {**state["robot"], "radius_cm": ROBOT_RADIUS_CM}
    objects = [{**obj, "size_cm": OBJECT_SIZE_CM} for obj in state["objects"]]
    xs = [0, 400, robot["x"]]
    ys = [0, robot["y"]]
    for obstacle in obstacles:
        xs.extend((obstacle["x_min"], obstacle["x_max"]))
        ys.extend((obstacle["y_min"], obstacle["y_max"]))
    for obj in objects:
        xs.append(obj["x"])
        ys.append(obj["y"])

    scenario = env.scenario
    receipts = env.last_readings()
    sensors: dict[str, dict[str, Any] | None] = dict.fromkeys(
        ("lidar_front", "ultrasonic_front", "camera_front")
    )
    distance_sensors = (*scenario.lidars, scenario.ultrasonic)
    for cfg in distance_sensors:
        if cfg is not None:
            raw = receipts.get(cfg.name)
            sensors[cfg.name] = dict(raw, range_cm=cfg.max_range_cm) if raw else None
    camera = scenario.camera
    raw = receipts.get(camera.name)
    sensors[camera.name] = (
        dict(raw, fov_deg=camera.fov_deg, range_cm=camera.max_range_cm) if raw else None
    )
    sensors[scenario.position.name] = receipts.get(scenario.position.name)

    return {
        "sim_time": state["time"],
        "world": {
            "scenario": state["scenario"],
            "bounds_cm": {
                "x_min": min(xs) - FLOOR_MARGIN_CM,
                "x_max": max(xs) + FLOOR_MARGIN_CM,
                "y_min": min(ys) - FLOOR_MARGIN_CM,
                "y_max": max(ys) + FLOOR_MARGIN_CM,
            },
            "robot": robot,
            "obstacles": obstacles,
            "objects": objects,
            "lighting": {"color": state["lighting"]["name"]},
            "sensors": sensors,
        },
    }
