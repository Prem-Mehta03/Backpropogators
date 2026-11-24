"""Frame recorder: one world snapshot per tool call, for the 3-D viewer and replays (D15).

This is composition-root code (scripts/), not a layer. It is the only place that looks at the
simulated world and at memory side by side: the agent loop tells it about every tool call
(`on_step`), and it stores a frame in the format of Appendix B of the handoff:
    {step, sim_time, tool {name, args, ok, auto}, world {...}, beliefs [...]}
Frame 0 is captured before the first model call. A trace keeps the list under "frames".

The world part comes from `sensorimotor.world_view.export_frame(env)` once Asvin's A4 lands. Until
then `basic_world(env)` builds the same shape from `env.get_state()`, so the recorder and the
viewer can be developed without waiting. The viewer only draws what is in a frame; it never
computes a sensor value.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

ROBOT_RADIUS_CM = 20
WORLD_MARGIN_CM = 100
MIN_FORWARD_CM = 400
READING_KEYS = ("value", "status", "confidence")


def _load_export_frame() -> Callable[[Any], dict[str, Any]] | None:
    try:
        from sensorimotor.world_view import (
            export_frame,  # type: ignore[import-not-found]
        )
    except ImportError:
        return None
    return export_frame


def basic_world(env: Any, initial_obstacles: set[str], step: int) -> dict[str, Any]:
    """World part of a frame built from env.get_state(), until export_frame exists.

    Obstacles that were not in the world at frame 0 get added_at_step = the current step (so
    the viewer can show a cart appearing). Bounds cover everything with a margin.
    """
    state = env.get_state()
    robot = {**state["robot"], "radius_cm": ROBOT_RADIUS_CM}
    obstacles = [
        {
            "id": o["obstacle_id"],
            "x_min": o["x_min"],
            "y_min": o["y_min"],
            "x_max": o["x_max"],
            "y_max": o["y_max"],
            "material": o.get("material", "solid"),
            "added_at_step": None if o["obstacle_id"] in initial_obstacles else step,
        }
        for o in state["obstacles"]
    ]
    xs = [robot["x"], MIN_FORWARD_CM] + [
        v for o in obstacles for v in (o["x_min"], o["x_max"])
    ]
    ys = [robot["y"]] + [v for o in obstacles for v in (o["y_min"], o["y_max"])]
    xs += [o["x"] for o in state["objects"]]
    ys += [o["y"] for o in state["objects"]]
    return {
        "bounds_cm": {
            "x_min": min(xs) - WORLD_MARGIN_CM,
            "y_min": min(ys) - WORLD_MARGIN_CM,
            "x_max": max(xs) + WORLD_MARGIN_CM,
            "y_max": max(ys) + WORLD_MARGIN_CM,
        },
        "robot": robot,
        "obstacles": obstacles,
        "objects": [{**o, "size_cm": 30} for o in state["objects"]],
        "lighting": {"color": state["lighting"]["name"]},
        "sensors": {},
        "sim_time": state["time"],
    }


class FrameRecorder:
    """Collects frames. Inputs: the simulated environment, the memory, optional export function.

    Use: recorder.capture_initial() before run_agent, then run_agent(..., on_step=recorder.on_step),
    then recorder.frames. Never raises into the run: a failed capture is logged and skipped.
    """

    def __init__(
        self,
        env: Any,
        memory: Any,
        export_frame: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self._env = env
        self._memory = memory
        self._export = export_frame or _load_export_frame()
        self._initial_obstacles: set[str] = set()
        self._last_readings: dict[str, dict[str, Any]] = {}
        self.frames: list[dict[str, Any]] = []

    # -- world and memory ----------------------------------------------------------------
    def _world(self, step: int) -> tuple[dict[str, Any], str | None]:
        if self._export is not None:
            exported = copy.deepcopy(self._export(self._env))
            world = exported.get("world", exported)
            return world, exported.get("sim_time") or world.pop("sim_time", None)
        world = basic_world(self._env, self._initial_obstacles, step)
        return world, world.pop("sim_time", None)

    def _beliefs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._memory.snapshot()["nodes"])

    def _sensors(self, world: dict[str, Any]) -> None:
        """Fill sensor entries the world export left empty with the last tool reading."""
        sensors = world.setdefault("sensors", {})
        for name, reading in self._last_readings.items():
            if sensors.get(name) is None:
                sensors[name] = {k: reading[k] for k in READING_KEYS if k in reading}

    def _add(self, step: int, tool: dict[str, Any] | None) -> None:
        try:
            world, sim_time = self._world(step)
            self._sensors(world)
            self.frames.append(
                {
                    "step": step,
                    "sim_time": sim_time,
                    "tool": copy.deepcopy(tool),
                    "world": world,
                    "beliefs": self._beliefs(),
                }
            )
        except Exception:  # a frame is an observation; losing one must not stop the run
            logger.exception("could not record frame %d", step)

    # -- the two entry points ------------------------------------------------------------
    def capture_initial(self) -> None:
        """Frame 0: the world and memory before the first model call. Resets the recorder."""
        self.frames = []
        self._last_readings = {}
        state = self._env.get_state()
        self._initial_obstacles = {o["obstacle_id"] for o in state["obstacles"]}
        self._add(0, None)

    def on_step(
        self,
        step: int,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any],
        auto: bool,
    ) -> None:
        """The run_agent callback: record the world and memory right after one tool call."""
        data = result.get("data") if result.get("ok") else None
        if isinstance(data, dict) and isinstance(data.get("sensor"), str):
            self._last_readings[data["sensor"]] = data
        self._add(
            step,
            {
                "name": tool,
                "args": args,
                "ok": bool(result.get("ok")),
                "auto": auto,
                "result": result,
            },
        )
