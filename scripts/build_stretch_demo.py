"""Render a captioned 1080p demonstration from four recorded simulation traces."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess

from PIL import Image, ImageColor, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1920, 1080, 24
BG, PANEL, TEXT, MUTED, ACCENT = "#0d1625", "#162437", "#f0f5fc", "#a6bad3", "#66e3c4"
WINDOWS_FONT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

CHAPTERS = {
    "T01": ("Scenario A | Live evidence beats the map",
            "The map says clear. LiDAR measures the blocked route. Memory records the new reading and retains the old map."),
    "B_APPROACH": ("Scenario B | Three views of one box",
                   "The camera initially sees no box. The robot moves closer, then reports the brown camera label alongside the red and blue claims."),
    "T05": ("T05 | Two sensors disagree",
            "The red LiDAR ray passes through glass. The green ultrasonic cone stops at the panel. The map stays in memory and the conflict is disputed."),
    "T10": ("T10 | Recheck before moving",
            "A cart enters the clear corridor. The automatic LiDAR recheck finds it at 40 cm. The 100 cm move is cancelled."),
}


def font(size: int, bold: bool = False):
    """Load a readable font from Windows, or the bundled Pillow fallback."""
    path = WINDOWS_FONT / ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default(size=size)


def wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int,
            size: int = 32, fill: str = TEXT, bold: bool = False) -> int:
    """Draw a paragraph at a fixed column width and return the next row."""
    f = font(size, bold)
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=f) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=f)
        y += round(size * 1.33)
    return y


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    """Define a content panel on the video canvas."""
    draw.rounded_rectangle(box, radius=24, fill=PANEL, outline="#2d415a", width=2)


def base(title: str, kicker: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create a project-branded frame for a caption or measured trace."""
    im = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(im)
    draw.text((72, 56), kicker, font=font(25, True), fill=ACCENT)
    draw.text((72, 92), title, font=font(53, True), fill=TEXT)
    draw.text((72, 1028), "I, Agent  /  Team Backpropogators     •     Scripted model in a deterministic simulated world",
              font=font(22), fill=MUTED)
    return im, draw


def project_world(draw: ImageDraw.ImageDraw, world: dict, tool: dict) -> None:
    """Show the exact recorded world using an isometric floor and volumetric actors."""
    bounds = world["bounds_cm"]
    robot = world["robot"]
    xmin, xmax = bounds["x_min"], bounds["x_max"]
    ymin, ymax = bounds["y_min"], bounds["y_max"]
    scale = min(950 / max(1, xmax - xmin + (ymax - ymin) * .58),
                365 / max(1, (xmax - xmin) * .2 + (ymax - ymin) * .43 + 60))

    def point(x, y, z=0):
        return (120 + ((x - xmin) + .58 * (ymax - y)) * scale,
                703 + (-.20 * (x - xmin) - .43 * (y - ymin) - z) * scale)

    corners = [point(x, y) for x, y in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))]
    draw.polygon(corners, fill="#342c27" if world["lighting"].get("color") == "yellow" else "#202e45", outline="#6783a6", width=2)
    for x in range(math.ceil(xmin / 50) * 50, int(xmax) + 1, 50):
        draw.line([point(x, ymin), point(x, ymax)], fill="#40526d", width=2)
    for y in range(math.ceil(ymin / 50) * 50, int(ymax) + 1, 50):
        draw.line([point(xmin, y), point(xmax, y)], fill="#40526d", width=2)

    def cube(x0, y0, x1, y1, h, color, outline="#d6e6fa"):
        rgb = ImageColor.getrgb(color)
        shade = lambda factor: tuple(round(channel * factor) for channel in rgb)
        face = [point(x, y, z) for z in (0, h) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        draw.polygon([face[i] for i in (0, 1, 5, 4)], fill=shade(.72), outline=outline, width=2)
        draw.polygon([face[i] for i in (1, 2, 6, 5)], fill=shade(.5), outline=outline, width=2)
        draw.polygon(face[4:], fill=color, outline=outline, width=2)

    for obstacle in world["obstacles"]:
        glass = obstacle.get("material") == "glass"
        color = "#74bdd8" if glass else "#cc8554" if obstacle.get("added_at_step") is not None else "#8291a5"
        cube(obstacle["x_min"], obstacle["y_min"], obstacle["x_max"], obstacle["y_max"], 50, color)
        p = point(obstacle["x_max"], obstacle["y_min"], 60)
        draw.text(p, "GLASS" if glass else obstacle["id"], font=font(19, True), fill=TEXT)
    for item in world["objects"]:
        r = item.get("size_cm", 30) / 2
        color = item.get("true_color", "red")
        cube(item["x"] - r, item["y"] - r, item["x"] + r, item["y"] + r, 30, color)

    x, y = robot["x"], robot["y"]
    angle = math.radians(robot["heading_deg"])
    cube(x - 18, y - 14, x + 18, y + 14, 19, "#eef6fc", "#8ebeda")
    cube(x - 8, y - 8, x + 8, y + 8, 36, "#4de1bc")
    draw.line([point(x, y, 40), point(x + 28 * math.cos(angle), y + 28 * math.sin(angle), 40)],
              fill="#70fff0", width=6)

    names = {"read_lidar": "lidar_front", "read_ultrasonic": "ultrasonic_front", "read_camera": "camera_front"}
    sensor = names.get(tool.get("name"))
    data = (world["sensors"].get(sensor) or {}) if sensor else {}
    if not tool.get("ok") or not data:
        return
    value = data.get("value")
    if sensor == "lidar_front" and isinstance(value, (int, float)):
        end = point(x + value * math.cos(angle), y + value * math.sin(angle), 17)
        draw.line([point(x, y, 17), end], fill="#ff6469", width=6)
        if data["status"] == "blocked":
            draw.ellipse((end[0] - 8, end[1] - 8, end[0] + 8, end[1] + 8), fill="#ff6469")
    elif sensor in {"ultrasonic_front", "camera_front"}:
        radius = value if isinstance(value, (float, int)) else data.get("range_cm", 300)
        half_angle = math.radians(7.5 if sensor == "ultrasonic_front" else 30)
        points = [point(x, y, 22), point(x + radius * math.cos(angle - half_angle), y + radius * math.sin(angle - half_angle), 22),
                  point(x + radius * math.cos(angle + half_angle), y + radius * math.sin(angle + half_angle), 22)]
        draw.polygon(points, outline="#6cf4a9" if sensor == "ultrasonic_front" else "#ffd269", width=5)
        if sensor == "camera_front" and isinstance(value, dict) and value.get("object_id"):
            item = next(o for o in world["objects"] if o["object_id"] == value["object_id"])
            draw.text(point(item["x"], item["y"], 45), f"camera: {value['color']}  ({data['confidence']:.2f})",
                      font=font(24, True), fill="#ffe09c")


def scene(test_id: str, frame: dict, answer: str, last: bool) -> Image.Image:
    """Render a trace frame with sensor receipts, provenance, and captions."""
    title, caption = CHAPTERS[test_id]
    im, draw = base(title, "FINAL EVALUATION  /  TRACE REPLAY")
    panel(draw, (68, 186, 1165, 864))
    panel(draw, (1190, 186, 1852, 864))
    tool = frame["tool"] or {}
    world = frame["world"]
    x = 106
    draw.text((x, 221), f"Step {frame['step']}   |   {tool.get('name', 'initial state')}"
              + ("   [auto]" if tool.get("auto") else ""), fill=ACCENT, font=font(29, True))
    draw.text((x, 268), f"Robot x={world['robot']['x']:g} cm    •    {frame['sim_time']}",
              fill=MUTED, font=font(24))
    project_world(draw, world, tool)
    y = 730
    for name in ("lidar_front", "ultrasonic_front", "camera_front"):
        reading = world["sensors"].get(name)
        if reading:
            value = reading["value"]
            if isinstance(value, dict):
                value = value.get("color") or "nothing in view"
            value = f"{value:g} cm" if isinstance(value, (float, int)) else str(value)
            draw.text((x, y), f"{name}   •   {value}   •   {reading['status']}   •   {reading['confidence']:.2f}",
                      fill=TEXT, font=font(24))
            y += 33
    draw.text((1221, 222), "Belief memory", fill=ACCENT, font=font(35, True))
    y = 282
    if not frame["beliefs"]:
        y = wrapped(draw, "No records", 1221, y, 585, 25, MUTED)
    for item in frame["beliefs"][:5]:
        y = wrapped(draw, f"{item['belief_id']}   {item['object']}   ·   {item['status']}",
                    1221, y, 585, 26, TEXT if item["status"] == "active" else MUTED, True)
        y = wrapped(draw, f"{item['source'] or 'source missing'}  /  {item['perspective']}  /  {item['confidence']:.2f}",
                    1221, y, 585, 22, MUTED) + 15
    if tool.get("name") in {"move_forward", "move_backward"} and not tool.get("ok"):
        draw.rounded_rectangle((1221, 745, 1816, 826), radius=16, fill="#6c2839")
        draw.text((1245, 770), "MOVE CANCELLED  /  POSE UNCHANGED", fill=TEXT, font=font(25, True))
    panel(draw, (68, 881, 1852, 1000))
    wrapped(draw, answer if last else caption, 105, 903, 1708, 29)
    return im


def card(title: str, items: list[tuple[str, str]], kicker: str) -> Image.Image:
    """Render the architecture or results card."""
    im, draw = base(title, kicker)
    for index, (heading, detail) in enumerate(items):
        y = 205 + index * 201
        panel(draw, (70, y, 1850, y + 168))
        draw.text((116, y + 31), heading, fill=ACCENT, font=font(34, True))
        wrapped(draw, detail, 555, y + 38, 1205, 33)
    return im


def main() -> int:
    """Read named traces, make a 1080p frame sequence, and encode it with local Blender."""
    parser = argparse.ArgumentParser(description=__doc__)
    for case in CHAPTERS:
        parser.add_argument(f"--{case.lower().replace('_', '-')}", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    manifest = []

    def add(image: Image.Image, seconds: float) -> None:
        path = root / f"slide_{len(manifest):03}.png"
        image.save(path)
        manifest.append({"file": str(path), "frames": round(seconds * FPS)})

    add(card("I, Agent", [
        ("The question", "Can a language-model agent distinguish its memory, current observations, and the user's perspective?"),
        ("The mechanism", "It gathers evidence through typed tools, checks provenance and updates a traceable belief store."),
        ("The demonstration", "Four recorded simulated runs with a scripted model. The animation visualizes logged state and measurements."),
    ], "ARCHITECTURE VERIFICATION"), 10)
    add(card("How information flows", [
        ("1  Declarative", "Query beliefs with sources, confidence, time and perspective. Supersession preserves earlier records."),
        ("2  Sensorimotor", "Read the deterministic world using LiDAR, ultrasonic and camera results. Actions return the resulting pose."),
        ("3  Procedural", "Use the ReAct loop and the checklist. Validate evidence-bound writes and recheck before movement."),
    ], "THREE LAYERS  /  CONTRACT V1.1"), 12)
    for key in CHAPTERS:
        trace = json.loads(getattr(args, key.lower()).read_text(encoding="utf-8"))
        if trace["test_id"] != key or trace["labels"]["execution"] != "scripted_llm" or not trace["frames"]:
            raise ValueError(f"Expected recorded scripted trace for {key}")
        frames = trace["frames"]
        for i, frame in enumerate(frames):
            if i and (start := frames[i - 1]["world"]["robot"]) != frame["world"]["robot"]:
                for step in range(1, 13):
                    transition = deepcopy(frame)
                    end = transition["world"]["robot"]
                    for axis in ("x", "y", "heading_deg"):
                        end[axis] = start[axis] + (end[axis] - start[axis]) * step / 12
                    add(scene(key, transition, trace["answer"], False), 1 / FPS)
            add(scene(key, frame, trace["answer"], i == len(frames) - 1),
                8 if i == len(frames) - 1 else 3.5)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    scripted, live = summary["totals"]["scripted_llm"], summary["totals"]["live"]
    live_readout = f"{live['passes']}/{live['runs']} passing." if live["runs"] else "Hosted trials are pending."
    add(card("What the tests showed", [
        ("Scripted runs", f"{scripted['passes']}/{scripted['runs']} passes across ten acceptance tests, with {scripted['fallback_count']} fallback answers."),
        ("Observed safeguards", "The procedure rejected unsupported writes and cancelled movement when the recheck made travel unsafe."),
        ("Limits", f"The world is simulated; 3-D graphics visualize the 2-D physics. {live_readout} Downgrade and update remain separate operations."),
    ], "MEASURED RESULTS"), 13)
    total_frames = sum(slide["frames"] for slide in manifest)
    if total_frames > FPS * 180:
        raise ValueError("Demo exceeds the three-minute delivery limit")
    index = root / "sequence.json"
    index.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(args.blender.resolve()), "--background", "--factory-startup", "--python-exit-code", "1",
                    "--python", str(Path(__file__).with_name("encode_stretch_demo.py")), "--",
                    str(index), str(root / "I_Agent_Demo.mp4")], check=True)
    print(f"{total_frames / FPS:.1f} seconds at 1920×1080: {root / 'I_Agent_Demo.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
