"""Terminal demo view for the sensorimotor layer (printing is allowed here).

    python -m demo.app --scenario scenario_a --seed 42

Shows a top-down map, world state and a command prompt:
    lidar | camera [object_id] | pos | f <cm> | b <cm> | t <deg> | wait <s>
    reset | state | json on|off | help | quit

The belief, tool-call and answer panels need the other layers and are left as
a placeholder (``render_agent_panels``) until week 8.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from sensorimotor import Sensorimotor, create_sensorimotor, list_scenarios

MAP_WIDTH = 60
MAP_HEIGHT = 15
ARROWS = {0: ">", 1: "^", 2: "<", 3: "v"}


def render_map(state: dict) -> str:
    """ASCII top-down map: R robot (arrow shows heading), # obstacle, o object."""
    xs = [state["robot"]["x"]] + [o["x"] for o in state["objects"]]
    ys = [state["robot"]["y"]] + [o["y"] for o in state["objects"]]
    for ob in state["obstacles"]:
        xs += [ob["x_min"], ob["x_max"]]
        ys += [ob["y_min"], ob["y_max"]]
    x0, x1 = min(xs) - 10, max(xs) + 10
    y0, y1 = min(ys) - 10, max(ys) + 10
    sx, sy = (x1 - x0) / MAP_WIDTH or 1, (y1 - y0) / MAP_HEIGHT or 1
    grid = [["." for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

    def cell(x: float, y: float):
        c = min(MAP_WIDTH - 1, int((x - x0) / sx))
        r = min(MAP_HEIGHT - 1, int((y1 - y) / sy))
        return r, c

    for ob in state["obstacles"]:
        for c in range(MAP_WIDTH):
            for r in range(MAP_HEIGHT):
                x, y = x0 + (c + 0.5) * sx, y1 - (r + 0.5) * sy
                if ob["x_min"] <= x <= ob["x_max"] and ob["y_min"] <= y <= ob["y_max"]:
                    grid[r][c] = "#"
    for obj in state["objects"]:
        r, c = cell(obj["x"], obj["y"])
        grid[r][c] = "o"
    rr, rc = cell(state["robot"]["x"], state["robot"]["y"])
    grid[rr][rc] = ARROWS[int(((state["robot"]["heading_deg"] + 45) % 360) // 90)]
    return "\n".join("".join(row) for row in grid)


def render_state(sm: Sensorimotor) -> str:
    s = sm.env.get_state()
    lines = [
        f"scenario={s['scenario']} seed={s['seed']} step={s['step']} time={s['time']}",
        "robot x={x:.1f} y={y:.1f} heading={heading_deg:.0f} deg".format(**s["robot"]),
        f"lighting={s['lighting']['name']} shift={s['lighting']['color_shift']}",
        "obstacles: " + (", ".join(o["obstacle_id"] for o in s["obstacles"]) or "none"),
        "objects:   "
        + (", ".join(f"{o['object_id']}({o['true_color']})" for o in s["objects"]) or "none"),
        "",
        render_map(s),
        "legend: arrow=robot  #=obstacle  o=object",
    ]
    return "\n".join(lines)


def render_agent_panels() -> str:
    """PLACEHOLDER: beliefs / observations / tool calls / answer (needs other layers)."""
    return "[beliefs, tool calls and answer panels: pending integration]"


def summarize(result, as_json: bool) -> str:
    d = result  # tool functions already return validated envelope dicts
    if as_json:
        return json.dumps(d, indent=2)
    if not d["ok"]:
        e = d["error"]
        return f"ERROR {e['code']}: {e['message']} (retryable={e['retryable']})"
    r = d["data"]
    unit = f" {r['unit']}" if r["unit"] else ""
    return (
        f"{d['tool']}: {r['sensor']} value={r['value']}{unit} status={r['status']} "
        f"confidence={r['confidence']} at {r['timestamp']}"
    )


def handle(sm: Sensorimotor, line: str, as_json: bool) -> str | None:
    parts: list[str] = line.split()
    if not parts:
        return ""
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd == "lidar":
            return summarize(sm.sensors.read_lidar(*args[:1]), as_json)
        if cmd == "camera":
            return summarize(sm.sensors.read_camera(*args[:1]), as_json)
        if cmd == "pos":
            return summarize(sm.sensors.get_position(), as_json)
        if cmd in ("f", "b", "t"):
            fn = {
                "f": sm.actions.move_forward,
                "b": sm.actions.move_backward,
                "t": sm.actions.turn,
            }[cmd]
            return summarize(fn(float(args[0])), as_json)
        if cmd == "wait":
            sm.env.advance_time(float(args[0]))
            return f"time now {sm.env.now_iso()}"
        if cmd == "reset":
            sm.env.reset()
            return "reset to starting state"
        if cmd == "state":
            return render_state(sm)
    except (IndexError, ValueError):
        return "usage error; type 'help'"
    return (
        "commands: lidar, camera [id], pos, f <cm>, b <cm>, t <deg>, wait <s>, reset, state, quit"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sensorimotor terminal demo")
    ap.add_argument("--scenario", default="scenario_a", help=f"one of {list_scenarios()} or a path")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="print full ToolResult JSON")
    args = ap.parse_args(argv)
    logging.disable(logging.WARNING)
    sm = create_sensorimotor(args.scenario, args.seed)
    print(render_state(sm))
    print(render_agent_panels())
    for line in sys.stdin if not sys.stdin.isatty() else iter(lambda: input("> "), "quit"):
        line = line.strip()
        if line == "quit":
            break
        print(handle(sm, line, args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
