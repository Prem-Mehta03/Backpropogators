"""Deterministic mock world: pose, obstacles, objects, lighting, clock.

Rules this file keeps (Team Guidelines sections 2 and 6):
  * no LLM logic, no imports from other layers, no contract models
  * no global state: build one with ``MockEnvironment(scenario)``
  * no hidden randomness: noise is a pure function of (seed, sensor, step)
  * the same seed and scenario always give the same readings

Geometry: 2-D plane in cm, +x axis is heading 0 deg, positive turns are
counter-clockwise. Obstacles are axis-aligned rectangles that block movement
and LiDAR. Objects are visual only (camera); they do not block anything.
"""

from __future__ import annotations

import copy
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .config import (
    TS_FORMAT,
    LightingConfig,
    ObjectConfig,
    ObstacleConfig,
    ScenarioConfig,
    parse_timestamp,
)

_log = logging.getLogger(__name__)
ACTIONS = ("move_forward", "move_backward", "turn", "wait")


@dataclass(frozen=True)
class StepOutcome:
    """What one call to ``step`` actually did."""

    action: str
    requested: float
    executed: float
    blocked: bool
    step: int
    timestamp: str


def ray_aabb(ox: float, oy: float, dx: float, dy: float, ob: ObstacleConfig) -> float | None:
    """Distance along a unit ray to a rectangle (slab method), or None if missed."""
    tmin, tmax = 0.0, math.inf
    for origin, d, lo, hi in (
        (ox, dx, ob.x_min, ob.x_max),
        (oy, dy, ob.y_min, ob.y_max),
    ):
        if abs(d) < 1e-12:
            if origin < lo or origin > hi:
                return None
        else:
            t1, t2 = (lo - origin) / d, (hi - origin) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin


class MockEnvironment:
    """The simulated world. Sensors and actions read and change it."""

    def __init__(self, scenario: ScenarioConfig, seed: int | None = None) -> None:
        self._scenario = scenario
        self._seed = scenario.seed if seed is None else int(seed)
        self.reset()

    # ------------------------------------------------------------ lifecycle
    def reset(self, seed: int | None = None) -> None:
        """Restore the exact starting state.

        Keeps the current seed; pass ``seed`` to switch to a different one.
        """
        sc = self._scenario
        if seed is not None:
            self._seed = int(seed)
        self._step = 0
        self._clock: datetime = parse_timestamp(sc.start_time)
        self._x, self._y, self._heading = sc.robot.x, sc.robot.y, sc.robot.heading_deg
        self._lighting: LightingConfig = sc.lighting
        self._obstacles: list[ObstacleConfig] = list(sc.obstacles)
        self._objects: dict[str, ObjectConfig] = {o.object_id: o for o in sc.objects}
        self._applied: set[int] = set()
        self._apply_due_events()
        _log.info("Environment reset: %s seed=%s", sc.name, self._seed)

    # ----------------------------------------------------------- properties
    @property
    def scenario(self) -> ScenarioConfig:
        return self._scenario

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def step_count(self) -> int:
        return self._step

    @property
    def pose(self) -> dict[str, float]:
        return {"x": self._x, "y": self._y, "heading_deg": self._heading}

    @property
    def lighting(self) -> LightingConfig:
        return self._lighting

    @property
    def objects(self) -> dict[str, ObjectConfig]:
        return dict(self._objects)

    def now_iso(self) -> str:
        """Simulated time, ISO 8601 UTC with trailing Z."""
        return self._clock.strftime(TS_FORMAT)

    # ----------------------------------------------------------------- time
    def advance_time(self, seconds: float) -> None:
        """Move the simulated clock forward without acting (staleness control).

        Does not count as a step and does not trigger step-based events.
        """
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("seconds must be a finite number >= 0")
        self._clock += timedelta(seconds=seconds)

    # ------------------------------------------------------------- geometry
    def ray_distance(self, offset_deg: float, max_range_cm: float) -> float | None:
        """Distance to the nearest obstacle along heading+offset, or None.

        None means nothing within ``max_range_cm``.
        """
        angle = math.radians(self._heading + offset_deg)
        dx, dy = math.cos(angle), math.sin(angle)
        hits = [
            t for ob in self._obstacles if (t := ray_aabb(self._x, self._y, dx, dy, ob)) is not None
        ]
        if not hits:
            return None
        nearest = min(hits)
        return nearest if nearest <= max_range_cm else None

    def noise(self, key: str, std: float) -> float:
        """Deterministic gaussian noise: pure function of (seed, key, step)."""
        if std <= 0:
            return 0.0
        return random.Random(f"{self._seed}|{key}|{self._step}").gauss(0.0, std)

    # --------------------------------------------------------------- action
    def step(self, action: str, amount: float = 0.0) -> StepOutcome:
        """Apply one action, then advance one tick (step counter and clock).

        ``move_*`` stops short of obstacles (collision margin); ``turn`` rotates;
        ``wait`` only advances time. Raises ValueError for an unknown action;
        argument validation for tools is done in ``actions.py``.
        """
        if action not in ACTIONS:
            raise ValueError(f"Unknown action {action!r}; expected one of {ACTIONS}")
        executed, blocked = 0.0, False
        if action in ("move_forward", "move_backward"):
            offset = 0.0 if action == "move_forward" else 180.0
            allowed = float(amount)
            hit = self.ray_distance(offset, math.inf)
            if hit is not None:
                allowed = min(allowed, max(0.0, hit - self._scenario.collision_margin_cm))
            blocked = allowed < float(amount) - 1e-9
            rad = math.radians(self._heading + offset)
            self._x += allowed * math.cos(rad)
            self._y += allowed * math.sin(rad)
            executed = allowed
        elif action == "turn":
            self._heading = (self._heading + float(amount)) % 360.0
            executed = float(amount)
        self._step += 1
        self._clock += timedelta(seconds=self._scenario.tick_seconds)
        self._apply_due_events()
        return StepOutcome(action, float(amount), executed, blocked, self._step, self.now_iso())

    # -------------------------------------------------------- world changes
    def apply_change(self, change: dict[str, Any]) -> None:
        """Change the world mid-run (test 10 hook). Types: see config.CHANGE_TYPES.

        {"type": "add_obstacle", "obstacle": {obstacle_id, x_min, y_min, x_max, y_max}}
        {"type": "remove_obstacle", "obstacle_id": "..."}
        {"type": "set_lighting", "lighting": {"name": "...", "color_shift": {...}}}
        {"type": "set_object_color", "object_id": "...", "true_color": "..."}
        """
        kind = change.get("type")
        if kind == "add_obstacle":
            o = change["obstacle"]
            self._obstacles.append(
                ObstacleConfig(o["obstacle_id"], o["x_min"], o["y_min"], o["x_max"], o["y_max"])
            )
        elif kind == "remove_obstacle":
            oid = change["obstacle_id"]
            self._obstacles = [o for o in self._obstacles if o.obstacle_id != oid]
        elif kind == "set_lighting":
            lt = change["lighting"]
            self._lighting = LightingConfig(lt["name"], dict(lt.get("color_shift", {})))
        elif kind == "set_object_color":
            obj = self._objects[change["object_id"]]
            self._objects[obj.object_id] = ObjectConfig(
                obj.object_id, obj.x, obj.y, change["true_color"]
            )
        else:
            raise ValueError(f"Unknown change type {kind!r}")
        _log.info("World change applied at step %s: %s", self._step, kind)

    def _apply_due_events(self) -> None:
        for idx, ev in enumerate(self._scenario.events):
            if idx not in self._applied and ev.at_step <= self._step:
                self.apply_change(dict(ev.change))
                self._applied.add(idx)

    # ---------------------------------------------------------------- state
    def get_state(self) -> dict[str, Any]:
        """Deep-copied plain-dict snapshot (for tests, logs and the demo view)."""
        return copy.deepcopy(
            {
                "scenario": self._scenario.name,
                "seed": self._seed,
                "step": self._step,
                "time": self.now_iso(),
                "robot": self.pose,
                "lighting": {
                    "name": self._lighting.name,
                    "color_shift": dict(self._lighting.color_shift),
                },
                "obstacles": [
                    {
                        "obstacle_id": o.obstacle_id,
                        "x_min": o.x_min,
                        "y_min": o.y_min,
                        "x_max": o.x_max,
                        "y_max": o.y_max,
                    }
                    for o in self._obstacles
                ],
                "objects": [
                    {
                        "object_id": o.object_id,
                        "x": o.x,
                        "y": o.y,
                        "true_color": o.true_color,
                    }
                    for o in self._objects.values()
                ],
            }
        )
