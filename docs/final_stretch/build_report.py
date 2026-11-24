"""Build the four-page evaluation report from the verified final run receipts."""

import argparse
from html import escape
import json
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle


ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/Prem-Mehta03/Backpropogators"
W, H = A4
M = 2 * cm
WIDTH = W - 2 * M
INK = colors.HexColor("#172845")
TEXT = colors.HexColor("#243348")
TEAL = colors.HexColor("#146e70")
MUTED = colors.HexColor("#52647a")
BORDER = colors.HexColor("#d7e1e8")
LIGHT = colors.HexColor("#f1f6f8")
RED = colors.HexColor("#a23632")


def load(path: Path) -> dict:
    """Read one emitted JSON evidence record."""
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(logs: Path, summary: dict, tid: str, run_id: str | None = None) -> tuple[dict, dict]:
    """Use the first measured scripted receipt for a figure and its caption."""
    if run_id is None:
        run_id = summary["tests"][tid]["scripted_llm"]["receipts"][0]["run_id"]
    stem = f"{tid}__{run_id}"
    paths = list(logs.rglob(f"{stem}.json"))
    if len(paths) != 1:
        raise ValueError(f"Expected one final receipt for {stem}, got {len(paths)}")
    record = load(paths[0])
    trace = load(paths[0].with_name(record["trace_file"]))
    if record["run_id"] != trace["run_id"] or record["result"] != "PASS":
        raise ValueError(f"A verified passing trace is required for {tid}")
    return record, trace


def text_style(name: str) -> ParagraphStyle:
    """Return print styles with an 11-point body, tables and captions."""
    options = {
        "body": ("Helvetica", 11, 15.5, TEXT),
        "label": ("Helvetica-Bold", 11, 14, TEAL),
        "caption": ("Helvetica", 11, 14, MUTED),
        "title": ("Helvetica-Bold", 25, 29, INK),
        "h1": ("Helvetica-Bold", 19, 23, INK),
        "h2": ("Helvetica-Bold", 13, 16, INK),
        "small-table": ("Helvetica", 11, 13, TEXT),
        "table-head": ("Helvetica-Bold", 11, 13, colors.white),
    }
    font, size, leading, color = options[name]
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading,
                          textColor=color, alignment=TA_LEFT, splitLongWords=False)


class Report:
    """Keep each self-contained page within fixed A4 print margins."""

    def __init__(self, output: Path) -> None:
        self.doc = canvas.Canvas(str(output), pagesize=A4, invariant=1, pageCompression=1)
        self.doc.setTitle("I, Agent Architecture Verification Report")
        self.doc.setAuthor("Team Backpropogators")
        self.page = 0
        self.y = 0.0

    def start(self, topic: str) -> None:
        """Open the next numbered page and draw its running label."""
        if self.page:
            self.doc.showPage()
        self.page += 1
        self.y = H - M
        self.paragraph(topic, "label", after=12)
        self.doc.setFont("Helvetica", 11)
        self.doc.setFillColor(MUTED)
        self.doc.drawString(M, M + 1, "I, Agent  /  Team Backpropogators")
        self.doc.drawRightString(W - M, M + 1, f"{self.page} / 4")

    def reserve(self, height: float, after: float) -> float:
        """Reserve a block or raise instead of clipping it into the footer."""
        bottom = self.y - height
        if bottom < M + 23:
            raise ValueError(f"Page {self.page} overflows by {M + 23 - bottom:.1f} pt")
        self.y = bottom - after
        return bottom

    def paragraph(self, text: str, style: str = "body", after: float = 9) -> None:
        """Draw a wrapping paragraph with simple ReportLab markup."""
        p = Paragraph(text, text_style(style))
        _, height = p.wrap(WIDTH, H)
        p.drawOn(self.doc, M, self.reserve(height, after))

    def table(self, head: list[str], rows: list[list[str]], dims: list[int], padding: int = 5) -> None:
        """Draw a body-size table with repeatable alternating rows."""
        values = [[Paragraph(val, text_style("table-head")) for val in head]] + [
            [Paragraph(val, text_style("small-table")) for val in row] for row in rows
        ]
        table = Table(values, colWidths=[WIDTH * d / sum(dims) for d in dims], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
            ("LINEBELOW", (0, -1), (-1, -1), 0.65, BORDER),
        ]))
        _, height = table.wrap(WIDTH, H)
        table.drawOn(self.doc, M, self.reserve(height, 10))

    def close(self) -> None:
        """Finish exactly four pages."""
        if self.page != 4:
            raise ValueError("Expected four report pages")
        self.doc.save()


def line(doc: canvas.Canvas, start: tuple[float, float], end: tuple[float, float], color=TEAL) -> None:
    """Draw a line ending in an arrowhead."""
    x, y = end
    angle = math.atan2(y - start[1], x - start[0])
    doc.setStrokeColor(color)
    doc.setLineWidth(1.4)
    doc.line(*start, *end)
    for offset in (-0.48, 0.48):
        dx = 5.4 * math.cos(angle + offset)
        dy = 5.4 * math.sin(angle + offset)
        doc.line(x, y, x - dx, y - dy)


def box(doc: canvas.Canvas, x: float, y: float, width: float, height: float,
        title: str, subtitle: str, fill=LIGHT) -> None:
    """Draw a title and subtitle in a diagram node."""
    doc.setStrokeColor(BORDER)
    doc.setFillColor(fill)
    doc.roundRect(x, y, width, height, 6, stroke=1, fill=1)
    doc.setFillColor(INK)
    doc.setFont("Helvetica-Bold", 11)
    doc.drawCentredString(x + width / 2, y + height / 2 + 4, title)
    doc.setFont("Helvetica", 11)
    doc.drawCentredString(x + width / 2, y + height / 2 - 12, subtitle)


def architecture(r: Report) -> None:
    """Draw the three runtime layers and the observer outside their tool calls."""
    d = r.doc
    y = r.reserve(150, 7)
    left, middle, right = M, M + 175, M + 350
    d.setFillColor(LIGHT)
    d.setStrokeColor(BORDER)
    d.roundRect(M, y, WIDTH, 150, 7, fill=1, stroke=1)
    d.setFont("Helvetica-Bold", 11)
    d.setFillColor(TEAL)
    d.drawCentredString(M + WIDTH / 2, y + 129, "Question in  /  Answer or typed error out")
    for x, title, subtitle in ((left, "Declarative", "Beliefs and history"),
                               (middle, "Procedural", "Model and tool loop"),
                               (right, "Sensorimotor", "World and sensors")):
        box(d, x + 7, y + 66, 124, 48, title, subtitle, colors.white)
    line(d, (left + 132, y + 94), (middle + 6, y + 94))
    line(d, (middle + 6, y + 84), (left + 132, y + 84))
    line(d, (middle + 132, y + 94), (right + 6, y + 94))
    line(d, (right + 6, y + 84), (middle + 132, y + 84))
    d.setFillColor(INK)
    d.setFont("Helvetica-Bold", 11)
    d.drawCentredString(M + WIDTH / 2, y + 47, "Tool calls and v1.1 contracts")
    d.setStrokeColor(BORDER)
    d.line(M + 20, y + 34, W - M - 20, y + 34)
    d.setFont("Helvetica", 11)
    d.drawCentredString(M + WIDTH / 2, y + 16, "Observer: evaluation trace and 3-D frame replay")


def belief_chain(r: Report, log: dict) -> None:
    """Derive the figure from the three actual stored T01 belief records."""
    nodes = log["state_after"]["memory"]["nodes"]
    if len(nodes) != 3 or any(nodes[i]["supersedes"] != nodes[i-1]["belief_id"] for i in (1, 2)):
        raise ValueError("The current T01 trace does not contain the illustrated three-node chain")
    d = r.doc
    y = r.reserve(53, 6)
    x_positions = [M, M + 176, M + WIDTH - 134]
    for x, node in zip(x_positions, nodes):
        box(d, x, y + 1, 134, 48, f"{node['belief_id']}  |  {node['confidence']:.2f}",
            f"{node['object']}, {node['status']}")
    for i in (1, 2):
        line(d, (x_positions[i] - 2, y + 25), (x_positions[i-1] + 136, y + 25))


def glass_figure(r: Report, trace: dict, screenshot: Path | None,
                 viewport: tuple[int, int, int, int] | None) -> str:
    """Use a supplied replay screenshot or draw an explicitly labelled T05 trace illustration."""
    frame = next(f for f in trace["frames"] if f["tool"] and f["tool"]["name"] == "read_ultrasonic")
    world = frame["world"]
    far = world["sensors"]["lidar_front"]["value"]
    near = world["sensors"]["ultrasonic_front"]["value"]
    if screenshot:
        img = ImageReader(str(screenshot))
        width, height = img.getSize()
        left, top, visible_w, visible_h = viewport or (0, 0, width, height)
        if (min(left, top) < 0 or min(visible_w, visible_h) <= 0
                or left + visible_w > width or top + visible_h > height):
            raise ValueError("Figure 3 crop lies outside the supplied image")
        scale = min(WIDTH / visible_w, 155 / visible_h)
        y = r.reserve(visible_h * scale, 6)
        x = M + (WIDTH - visible_w * scale) / 2
        r.doc.saveState()
        clip = r.doc.beginPath()
        clip.rect(x, y, visible_w * scale, visible_h * scale)
        r.doc.clipPath(clip, stroke=0, fill=0)
        r.doc.drawImage(img, x - left * scale, y - (height - top - visible_h) * scale,
                        width * scale, height * scale, mask="auto")
        r.doc.restoreState()
        return (f"T05 offline replay still. The LiDAR ray passes through glass and reports {far} cm. "
                f"The ultrasonic reading is {near} cm.")

    d = r.doc
    y = r.reserve(114, 6)
    glass = next(o for o in world["obstacles"] if o["material"] == "glass")

    def point(x: float, side: float, z: float = 0) -> tuple[float, float]:
        return M + 66 + 1.30 * x + 0.40 * side, y + 30 + 0.085 * x - 0.32 * side + z

    def polygon(points: list, fill, stroke=BORDER) -> None:
        p = d.beginPath()
        p.moveTo(*points[0])
        for pt in points[1:]:
            p.lineTo(*pt)
        p.close()
        d.setFillColor(fill)
        d.setStrokeColor(stroke)
        d.drawPath(p, fill=1, stroke=1)

    polygon([point(-27, -65), point(265, -65), point(265, 65), point(-27, 65)], LIGHT)
    for x in range(0, 251, 25):
        d.setStrokeColor(BORDER)
        d.setLineWidth(0.5)
        d.line(*point(x, -65), *point(x, 65))
    robot = point(world["robot"]["x"], world["robot"]["y"], 4)
    d.setFillColor(INK)
    d.ellipse(robot[0] - 12, robot[1] - 6, robot[0] + 12, robot[1] + 6, fill=1, stroke=0)
    glass_x = glass["x_min"]
    polygon([point(glass_x, glass["y_min"]), point(glass_x, glass["y_max"]),
             point(glass_x, glass["y_max"], 31), point(glass_x, glass["y_min"], 31)],
            colors.HexColor("#d8f3f4"), TEAL)
    line(d, point(0, 0, 11), point(float(far), 0, 11), TEAL)
    line(d, point(0, 0, 5), point(float(near), 0, 5), RED)
    d.setFont("Helvetica", 11)
    d.setFillColor(INK)
    d.drawString(M + 8, y + 94, f"Glass at {near} cm")
    d.setFillColor(TEAL)
    d.drawString(M + 254, y + 93, f"LiDAR: {far} cm, clear")
    d.setFillColor(RED)
    d.drawString(M + 254, y + 78, f"Ultrasonic: {near} cm, blocked")
    return "Isometric illustration derived from the T05 logged frame and both actual readings."


CASES = [
    ("Clear map, blocked route", "Keep the downgraded map in history and use LiDAR."),
    ("Blocked map, clear route", "Use the newer clear reading and cite times and confidence."),
    ("Three colour reports", "Attribute user, camera and bot views separately."),
    ("Weak sensor reading", "Keep the strong map and dispute the weak reading."),
    ("Glass and sensor disagreement", "Retain both readings, keep the map and request evidence."),
    ("Stale route evidence", "Keep closed history and use the current plan and reading."),
    ("No evidence for box", "Report missing evidence and leave the colour unknown."),
    ("False user claim", "Store it as user evidence and decline unsafe movement."),
    ("Missing provenance", "Cap confidence and answer from sourced evidence."),
    ("Obstacle appears mid-run", "Recheck, cancel the move and preserve the pose."),
]


def href(url: str, label: str) -> str:
    """Format an ordinary clickable source link."""
    return f'<link href="{escape(url, quote=True)}" color="{TEAL.hexval()}"><u>{escape(label)}</u></link>'


def build(output: Path, summary: dict, logs: Path, revision: str | None, screenshot: Path | None,
          viewport: tuple[int, int, int, int] | None, screenshot_run: str | None) -> None:
    """Build the four print pages using scoped results and raw traces."""
    first, _ = evidence(logs, summary, "T01")
    fifth, fifth_trace = evidence(logs, summary, "T05", screenshot_run)
    tenth, _ = evidence(logs, summary, "T10")
    manual, automatic = [step for step in tenth["tool_calls"] if step["tool"] == "read_lidar"]
    r = Report(output)
    r.start("ARCHITECTURE VERIFICATION  /  NOVEMBER 2026")
    r.paragraph("I, Agent", "title", after=5)
    r.paragraph("A Three-Layer Epistemic Architecture for Grounded Agents", "h2", after=12)
    r.paragraph("Vyom, Asvin, Prem and Yash  •  Team Backpropogators", "caption", after=17)
    r.paragraph("1  Problem and contribution", "h2", after=6)
    r.paragraph("An agent can repeat a stored fact after the world has changed or report a user's belief as its own observation. I, Agent keeps those sources distinct and makes their influence visible in a replayable trace. It draws on layered control in the 3T architecture and the tool interaction pattern of ReAct. Its contribution is a separate belief store with provenance and perspectives, a deterministic world, and checks in code for how evidence is used.", after=14)
    r.paragraph("2  Architecture and information flow", "h2", after=7)
    architecture(r)
    r.paragraph("<b>Figure 1.</b> Tool access connects the three implementations. The observer receives recorded state and outcomes for evaluation and replay.", "caption", after=12)
    r.paragraph("For a route question, the agent asks memory what was previously known and a distance sensor what is visible now. It compares the returns, requests a supported update when appropriate, and reports both the current reading and the previous claim. A tool result gives the model the evidence it may cite and gives the evaluator the data needed to check the outcome.")
    r.paragraph("Contract v1.1 adds ultrasonic evidence, shared policy constants and optional log metadata. Readers accept v1.0 and v1.1. The sensor layer exports read-only frames, and the composition root records a frame before the first tool call and after each call. The procedural layer receives tool data through its interface.")

    r.start("BELIEFS AND WORLD")
    r.paragraph("3a  Declarative layer", "h1", after=7)
    r.paragraph("A belief stores a subject, predicate and value with its source, confidence, timestamp, perspective, status and validity interval. A successor links to the record it supersedes. The earlier entry remains in history. User and third-party views are retained separately from conflicts among sensor and historical claims.", after=9)
    r.table(["Evidence rule", "Policy in contracts/policy.py"], [
        ["Strong current observation", "At least 0.6. Multiply prior confidence by 0.3 on downgrade."],
        ["Weak observation vs strong belief", "Below 0.5 vs at least 0.8. Keep prior and dispute new."],
        ["Missing source / stale history", "Confidence cap 0.5 / age over seven simulated days"],
    ], [45, 55], padding=4)
    belief_chain(r, first)
    r.paragraph(f"<b>Figure 2.</b> T01 {first['run_id']}. A downgrade creates a 0.30 successor, then the blocked LiDAR belief becomes active. Arrows point to the superseded records.", "caption", after=10)
    r.paragraph("3b  Sensorimotor layer and 3-D world", "h1", after=7)
    r.paragraph("The seeded 2-D world supports LiDAR, ultrasonic and camera readings. LiDAR passes through glass, while ultrasonic detects it. Camera colour depends on lighting. A scheduled obstacle can change a later reading. The 3-D observer adds display heights to recorded geometry and uses the original readings.", after=8)
    figure_caption = glass_figure(r, fifth_trace, screenshot, viewport)
    figure_source = escape(fifth["run_id"])
    r.paragraph(f"<b>Figure 3.</b> {figure_caption} Source: T05 {figure_source}.", "caption")

    r.start("REASONING AND SAFEGUARDS")
    r.paragraph("3c  Procedural layer and structural prompts", "h1", after=9)
    r.paragraph("The ReAct loop alternates model tool requests and typed results until it can give a final answer. Prompt v6 supplies the role, evidence rules and an answer format, with an optional entity glossary. It describes how to report stale, unsourced, disputed and low-confidence evidence, and how to distinguish viewpoints and disclose a cancelled move.", after=9)
    r.paragraph('“Before answering any question about the state of the world, call query_belief for the subject and the relevant sensor tool.” <i>Evidence policy, procedural/prompts.py</i>', "caption", after=13)
    r.paragraph("What runs in code", "h2", after=9)
    r.table(["Mechanism", "What the runtime checks"], [
        ["Tool results", "Memory and sensor APIs supply the evidence and typed errors used in the answer."],
        ["Evidence checklist", "Requires a lookup and the relevant sensor attempts before an answer is accepted."],
        ["Claim check", "Rejects unsupported memory claims and IDs. After repeated refusals, the system can summarize the logged evidence."],
        ["Provenance guard", "Checks evidence against a proposed write and rejects unsupported downgrades."],
        ["Automatic move recheck", "Re-reads available distance sensors. Blocking evidence or insufficient clearance cancels dispatch."],
    ], [34, 66], padding=6)
    r.paragraph("Scenario B", "h2", after=6)
    r.paragraph("T03 traces red to the user, brown to the camera and blue to the bot history. The three results carry their own sources. The answer can report the apparent colour without claiming to know the physical cause.")
    r.paragraph("Recheck before action", "h2", after=6)
    r.paragraph(f"T10 preserves the robot's starting pose. The model requests motion after the initial clear "
                f"reading of {manual['result']['data']['value']} cm. The automatic recheck records the new "
                f"obstacle at {automatic['result']['data']['value']} cm. The move returns CONFLICT before "
                "dispatch.")

    r.start("TEST RESULTS AND SOURCES")
    r.paragraph("4  Evaluation", "h1", after=7)
    offline = summary["totals"]["scripted_llm"]
    live = summary["totals"]["live"]
    r.paragraph(f"The actual layer code ran with an injected scripted model and fresh state per trial. The evaluator checks tool order and receipts, before/after belief and world state, and case-specific answer evidence. Offline: <b>{offline['passes']}/{offline['runs']}</b> passes, {offline['fallback_count']} fallback summaries. "
                + (f"Live: {live['passes']}/{live['runs']} passes, {live['fallback_count']} fallback summaries."
                   if live['runs'] else "No comparable hosted runs were available for the requested three per case.") , after=8)
    rows = []
    for i, (condition, expected) in enumerate(CASES, start=1):
        tid = f"T{i:02}"
        case = summary["tests"][tid]
        off, on = case["scripted_llm"], case["live"]
        rows.append([f"<b>{tid}</b> {condition}", expected,
                     f"{off['passes']}/{off['runs']}" if off['runs'] else "Not run",
                     f"{on['passes']}/{on['runs']}" if on['runs'] else "Not run"])
    r.table(["Condition", "Expected behaviour", "Offline", "Live"], rows, [30, 44, 12, 14], padding=4)
    r.paragraph("5  Limitations", "h2", after=5)
    r.paragraph("Typed tool data, evidence checks, claim checks, the write guard and automatic rechecks constrain unsupported responses. Open-ended answers remain harder to verify. The world is simulated in 2-D and drawn in 3-D. Scripted, scenario-specific trials do not estimate hosted 20B reliability. The two memory writes are separately transactional and can partially succeed.", after=8)
    r.paragraph("Evidence and references", "h2", after=6)
    repo_link = href(f"{REPO}/tree/{revision}" if revision else REPO, "Backpropogators repository")
    table_path = "evaluation/results/results_table.md"
    table_link = href(f"{REPO}/blob/{revision}/{table_path}", "results table") if revision else table_path
    r.paragraph(f"{repo_link}  •  {table_link}. Run records are in <font face='Courier'>evaluation/logs/final/</font>. "
                "The team review and final tag remain pending.", "body", after=7)
    r.paragraph("Backpropogators, <i>I, Agent</i> project proposal and final-stretch handoff. "
                f"Yao et al., {href('https://arxiv.org/abs/2210.03629', 'ReAct')} (ICLR 2023). "
                f"Bonasso et al., {href('https://doi.org/10.1080/095281397147103', 'Experiences with an architecture for intelligent, reactive agents')} (1997).", after=0)
    r.close()


def main() -> None:
    """Read measured evidence and write the print-ready PDF to a new path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "evaluation/results/summary.json")
    parser.add_argument("--logs", type=Path, default=ROOT / "evaluation/logs/final")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", help="Reviewed repository branch, tag or commit for evidence links")
    parser.add_argument("--screenshot", type=Path, help="Still of the T05 replay for Figure 3")
    parser.add_argument("--screenshot-run", help="Run ID of the supplied T05 replay still")
    parser.add_argument("--viewport", type=int, nargs=4, metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
                        help="Clip the supplied still to the T05 replay viewport in pixels")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path to preserve previous reports")
    if bool(args.screenshot) != bool(args.screenshot_run):
        parser.error("Provide --screenshot and --screenshot-run together")
    if args.viewport and not args.screenshot:
        parser.error("--viewport needs --screenshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(args.output, load(args.summary), args.logs, args.revision, args.screenshot,
          tuple(args.viewport) if args.viewport else None, args.screenshot_run)


if __name__ == "__main__":
    main()
