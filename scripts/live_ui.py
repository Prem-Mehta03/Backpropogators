#!/usr/bin/env python3
# ruff: noqa: E501, BLE001
"""Live demo UI for the I, Agent procedural layer.

Starts a small local web server (standard library only). The page in ui/live/ is a chat box
with a 3D belief graph and a live step trace. Every question runs the real agent loop
(procedural.agent.run_agent) against the real declarative and sensorimotor layers, exactly like
scripts/ask_agent.py, and streams each model call and tool call to the page as it happens.

    python scripts/live_ui.py                      # live: needs GROQ_API_KEY like ask_agent.py
    python scripts/live_ui.py --replay trace.json  # no model calls: play recorded frames
    python scripts/live_ui.py --replay             # legacy recorded conversations
    python scripts/live_ui.py --scenario scenario_b --port 8765

Memory persists between questions in one session, so a downgrade or a person's answer shows up
in the graph and in later answers. "Reset" rebuilds the world from the seed.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
UI_DIR = ROOT / "ui" / "live"
LOG_DIR = ROOT / "evaluation" / "logs"

SUBJECTS = {
    "path_A": "the path ahead of the robot (the route the robot would take)",
    "box_01": "the box the user is asking about",
    "robot": "this robot itself",
}
SCENARIOS = tuple(sorted(p.stem for p in (ROOT / "sensorimotor" / "scenarios").glob("*.json")))
SENSOR_TOOLS = ("read_lidar", "read_ultrasonic", "read_camera")
MEMORY_WRITES = ("update_belief", "downgrade_belief")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plain(value: Any) -> Any:
    """Turn model objects into JSON-friendly data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def envelope_data(result: Any) -> Any:
    result = plain(result)
    if isinstance(result, dict) and "ok" in result:
        return result.get("data") if result.get("ok") else None
    return result


class SessionState:
    """What the graph shows: every belief and sensor reading seen or written this session."""

    def __init__(self) -> None:
        self.beliefs: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []
        self.counter = 0

    def absorb(self, tool: str, args: dict[str, Any], result: Any, run_no: int) -> None:
        data = envelope_data(result)
        if data is None:
            return
        if tool == "query_belief" and isinstance(data, list):
            for item in data:
                self._add_belief(item)
        elif tool in MEMORY_WRITES and isinstance(data, dict):
            self._add_belief(data, written_in_run=run_no)
        elif tool in SENSOR_TOOLS and isinstance(data, dict):
            self._add_observation(tool, args, data, run_no)

    def _add_belief(
        self, item: dict[str, Any], written_in_run: int | None = None
    ) -> None:
        bid = item.get("belief_id")
        if not isinstance(bid, str):
            return
        old = self.beliefs.get(bid, {})
        merged = {**old, **item}
        if written_in_run is not None:
            merged["written_in_run"] = written_in_run
        self.beliefs[bid] = merged
        parent = item.get("supersedes")
        if parent and parent in self.beliefs:
            self.beliefs[parent]["superseded_by"] = bid

    def _add_observation(
        self, tool: str, args: dict[str, Any], data: dict[str, Any], run_no: int
    ):
        value = data.get("value")
        if tool == "read_camera" and isinstance(value, dict):
            subject = value.get("object_id") or args.get("target")
            predicate, obj = "color", value.get("color")
        else:
            subject, predicate, obj = "path_A", "status", data.get("status")
        key = f"{data.get('sensor')}|{subject}|{predicate}"
        entry = {
            "key": key,
            "sensor": data.get("sensor"),
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "value": value,
            "unit": data.get("unit"),
            "confidence": data.get("confidence"),
            "timestamp": data.get("timestamp"),
            "run": run_no,
        }
        self.observations = [o for o in self.observations if o["key"] != key] + [entry]

    def snapshot(self) -> dict[str, Any]:
        return {
            "beliefs": list(self.beliefs.values()),
            "observations": self.observations,
        }


class TracingLLM:
    """Wraps the real LLM client and reports each model call to the page."""

    def __init__(self, inner: Any, emit) -> None:
        self.inner, self.emit, self.n = inner, emit, 0

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        self.n += 1
        self.emit({"type": "model_call", "n": self.n})
        reply = self.inner.chat(*args, **kwargs)
        calls = [
            getattr(c, "name", "?") for c in (getattr(reply, "tool_calls", None) or [])
        ]
        self.emit(
            {
                "type": "model_reply",
                "n": self.n,
                "text": getattr(reply, "content", "") or "",
                "tools": calls,
            }
        )
        return reply


def pick_registry(built: Any) -> dict[str, Any]:
    if isinstance(built, dict) and "query_belief" in built:
        return built
    if isinstance(built, (tuple, list)):
        for part in built:
            if isinstance(part, dict) and "query_belief" in part:
                return part
    for attr in ("registry", "tools"):
        part = getattr(built, attr, None)
        if isinstance(part, dict) and "query_belief" in part:
            return part
    raise RuntimeError("build_tool_registry returned no registry with query_belief")


class LiveSession:
    def __init__(
        self, scenario: str, replay: bool, replay_trace: dict[str, Any] | None = None
    ) -> None:
        self.scenario, self.replay = scenario, replay
        self.replay_trace = replay_trace
        self.initial_frame: dict[str, Any] | None = None
        self.state = SessionState()
        self.run_no = 0
        self.busy = threading.Lock()
        self.registry: dict[str, Any] = {}
        self.memory: Any = None
        self.world: Any = None
        self.llm: Any = None
        self.error: str | None = None
        self.reset(scenario)

    # -- setup -------------------------------------------------------------------------
    def reset(self, scenario: str) -> None:
        self.scenario = scenario
        self.state = SessionState()
        self.run_no = 0
        self.error = None
        self.initial_frame = None
        if self.replay_trace is not None:
            self.initial_frame = self.replay_trace["frames"][0]
            return
        if self.replay:
            for subject, args in (("path_A", None), ("box_01", None)):
                env = REPLAY_SEED[subject]
                self.state.absorb("query_belief", {"subject": subject}, env, 0)
            return
        try:
            from scripts.tool_wiring import (  # type: ignore[import-not-found]
                build_memory,
                build_sensorimotor,
                build_tool_registry,
            )

            sensorimotor = build_sensorimotor(scenario)
            memory = build_memory(seed=True)
            self.memory, self.world = memory, sensorimotor
            built = build_tool_registry(
                use_real=True,
                memory=memory,
                sensorimotor=sensorimotor,
                scenario=scenario,
            )
            self.registry = pick_registry(built)
            from scripts.frame_recorder import FrameRecorder

            if memory is not None and sensorimotor is not None:
                initial = FrameRecorder(sensorimotor.env, memory)
                initial.capture_initial()
                self.initial_frame = initial.frames[0] if initial.frames else None
            if self.llm is None:
                try:
                    from dotenv import load_dotenv  # type: ignore[import-not-found]

                    load_dotenv(ROOT / ".env")
                except ImportError:
                    pass
                from procedural.llm_client import LLMClient

                self.llm = LLMClient()
            from procedural.tools import call_tool

            for subject in ("path_A", "box_01"):
                env = call_tool("query_belief", {"subject": subject}, self.registry)
                self.state.absorb("query_belief", {"subject": subject}, env, 0)
        except (
            Exception
        ) as exc:  # shown in the page, so the cause is visible while recording
            self.error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    # -- one question ------------------------------------------------------------------
    def ask(self, question: str, emit) -> None:
        self.run_no += 1
        emit(
            {
                "type": "start",
                "question": question,
                "run": self.run_no,
                "scenario": self.scenario,
            }
        )
        if self.error:
            emit(
                {
                    "type": "final",
                    "answer": "",
                    "error": {"code": "INTERNAL", "message": self.error},
                }
            )
            return
        if self.replay:
            self._ask_replay(question, emit)
            return
        from procedural.agent import run_agent
        from procedural.prompts import PROMPT_VERSION

        llm = TracingLLM(self.llm, emit)
        recorder = None
        if self.memory is not None and self.world is not None:
            from scripts.frame_recorder import FrameRecorder

            recorder = FrameRecorder(self.world.env, self.memory)
            recorder.capture_initial()  # frame 0, before the first model call
            if recorder.frames:
                emit({"type": "frame", "frame": recorder.frames[-1]})

        def capture_step(step, tool, args, result, auto):
            self.state.absorb(tool, args, result, self.run_no)
            emit({"type": "tool", "tool": tool, "args": args, "result": result, "auto": auto})
            emit({"type": "session", **self.state.snapshot()})
            if recorder is not None:
                count = len(recorder.frames)
                recorder.on_step(step, tool, args, result, auto)
                if len(recorder.frames) > count:
                    emit({"type": "frame", "frame": recorder.frames[-1]})
        try:
            result = run_agent(
                question,
                llm,
                self.registry,
                known_subjects=SUBJECTS,
                require_written_ids=True,
                on_step=capture_step,
            )
        except Exception as exc:
            traceback.print_exc()
            emit(
                {
                    "type": "final",
                    "answer": "",
                    "error": {"code": "INTERNAL", "message": str(exc)},
                }
            )
            return
        calls = plain(result.tool_calls)
        for entry in calls:  # authoritative copy: includes guard overrides and refusals
            self.state.absorb(
                entry["tool"], entry.get("args") or {}, entry["result"], self.run_no
            )
        final = {
            "type": "final",
            "answer": result.answer,
            "error": plain(result.error),
            "tool_calls": calls,
            "model_calls": result.model_calls,
            "evidence_nudges": result.evidence_nudges,
            "claim_nudges": result.claim_nudges,
            "claim_refusals": plain(result.claim_refusals),
            "answer_source": result.answer_source,
            "model": getattr(self.llm, "model", None),
            "prompt_version": PROMPT_VERSION,
            "answer_normalized": result.answer_normalized,
        }
        emit(final)
        emit({"type": "session", **self.state.snapshot()})
        self._write_log(question, final, recorder.frames if recorder else [])

    def _write_log(
        self, question: str, final: dict[str, Any], frames: list[dict[str, Any]]
    ) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            doc = {
                "run_id": now_iso(),
                "source": "live_ui",
                "scenario": self.scenario,
                "question": question,
                **final,
                "frames": frames,
            }
            (LOG_DIR / f"agent_run_live_{stamp}.json").write_text(
                json.dumps(doc, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def _ask_replay(self, question: str, emit) -> None:
        text = question.lower()
        key = (
            "A"
            if ("route" in text or "path" in text)
            else "D" if "box_99" in text else "B"
        )
        run = REPLAY_RUNS[key]
        for i, step in enumerate(run["calls"], 1):
            time.sleep(0.9)
            emit({"type": "model_call", "n": i})
            time.sleep(0.6)
            emit({"type": "model_reply", "n": i, "text": "", "tools": [step["tool"]]})
            self.state.absorb(step["tool"], step["args"], step["result"], self.run_no)
            emit(
                {
                    "type": "tool",
                    "tool": step["tool"],
                    "args": step["args"],
                    "result": step["result"],
                }
            )
            emit({"type": "session", **self.state.snapshot()})
        time.sleep(0.8)
        emit({"type": "model_call", "n": len(run["calls"]) + 1})
        time.sleep(0.6)
        emit(
            {
                "type": "model_reply",
                "n": len(run["calls"]) + 1,
                "text": run["answer"],
                "tools": [],
            }
        )
        calls = [
            {
                "step": i,
                "tool": s["tool"],
                "args": s["args"],
                "result": s["result"],
                **({"guard": s["guard"]} if "guard" in s else {}),
            }
            for i, s in enumerate(run["calls"], 1)
        ]
        emit(
            {
                "type": "final",
                "answer": run["answer"],
                "error": None,
                "tool_calls": calls,
                "model_calls": len(calls) + 1,
                "evidence_nudges": 0,
                "claim_nudges": run["claim_nudges"],
                "answer_normalized": True,
            }
        )
        emit({"type": "session", **self.state.snapshot()})


# ---- recorded data for --replay (copied from real runs of 2026-10-12) -------------------


def _belief(
    bid, subject, predicate, obj, source, conf, perspective, ts, supersedes=None
):
    return {
        "schema_version": "1.0",
        "belief_id": bid,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "source": source,
        "confidence": conf,
        "timestamp": ts,
        "perspective": perspective,
        "status": "active",
        "valid_from": ts,
        "valid_to": None,
        "supersedes": supersedes,
    }


def _ok(tool, data):
    return {
        "schema_version": "1.0",
        "tool": tool,
        "ok": True,
        "data": data,
        "error": None,
        "timestamp": "2026-10-12T20:29:00Z",
    }


_SEED = "2026-10-03T09:15:00Z"
_B1 = _belief(
    "b_000001", "path_A", "status", "clear", "default_map", 1.0, "historical", _SEED
)
_B2 = _belief("b_000002", "box_01", "color", "red", "user", 0.9, "user", _SEED)
_B3 = _belief(
    "b_000003", "box_01", "color", "blue", "bot_02", 0.8, "third_party", _SEED
)
REPLAY_SEED = {
    "path_A": _ok("query_belief", [_B1]),
    "box_01": _ok("query_belief", [_B2, _B3]),
}
_LIDAR = {
    "schema_version": "1.0",
    "sensor": "lidar_front",
    "value": 12,
    "unit": "cm",
    "status": "blocked",
    "timestamp": "2026-10-03T09:16:00Z",
    "confidence": 0.98,
}
_CAM = {
    "schema_version": "1.0",
    "sensor": "camera_front",
    "value": {"object_id": "box_01", "color": "brown"},
    "unit": None,
    "status": "clear",
    "timestamp": "2026-10-03T09:16:00Z",
    "confidence": 0.9,
}
_B4 = _belief(
    "b_000004",
    "path_A",
    "status",
    "clear",
    "default_map",
    0.3,
    "historical",
    "2026-10-12T20:28:23Z",
    "b_000001",
)
_B5 = _belief(
    "b_000005",
    "path_A",
    "status",
    "blocked",
    "lidar_front",
    0.98,
    "agent_sensor",
    "2026-10-12T20:28:51Z",
    "b_000004",
)

REPLAY_RUNS = {
    "A": {
        "claim_nudges": 1,
        "calls": [
            {
                "tool": "query_belief",
                "args": {"subject": "path_A"},
                "result": _ok("query_belief", [_B1]),
            },
            {
                "tool": "read_lidar",
                "args": {"direction": "front"},
                "result": _ok("read_lidar", _LIDAR),
            },
            {
                "tool": "downgrade_belief",
                "args": {
                    "belief_id": "b_000001",
                    "new_confidence": 0.3,
                    "reason": "Live lidar indicates obstacle",
                },
                "result": _ok("downgrade_belief", _B4),
                "guard": {
                    "overridden": {"new_confidence": {"model_value": 0.5, "used": 0.3}}
                },
            },
            {
                "tool": "update_belief",
                "args": {
                    "subject": "path_A",
                    "predicate": "status",
                    "object": "blocked",
                    "source": "lidar_front",
                    "confidence": 0.98,
                    "perspective": "agent_sensor",
                },
                "result": _ok("update_belief", _B5),
            },
        ],
        "answer": "No, my route is not clear.\nMy stored belief says the route (path_A) is clear (status: clear, source: default_map, confidence 1.0, perspective: historical).\nMy live lidar reading indicates the route is blocked (status: blocked, confidence 0.98).\nI have downgraded the stored belief b_000001 to b_000004 and recorded a new belief b_000005.\nMemory status: b_000004 (clear, default_map) is recorded as downgraded, b_000005 (blocked, lidar_front) is recorded as active.",
    },
    "B": {
        "claim_nudges": 0,
        "calls": [
            {
                "tool": "query_belief",
                "args": {"subject": "box_01", "predicate": "color"},
                "result": _ok("query_belief", [_B2, _B3]),
            },
            {
                "tool": "read_camera",
                "args": {"target": "box_01"},
                "result": _ok("read_camera", _CAM),
            },
        ],
        "answer": "The camera sees box_01 as brown.\n\nMy stored belief says the box is red (user, confidence 0.9) and also says it is blue (third_party, confidence 0.8). The live camera reading indicates the color is brown (confidence 0.9). I have not changed any belief. Tell me which one to treat as correct and I will record your answer as a belief.",
    },
    "D": {
        "claim_nudges": 0,
        "calls": [
            {
                "tool": "query_belief",
                "args": {"subject": "box_99"},
                "result": _ok("query_belief", []),
            },
            {
                "tool": "read_camera",
                "args": {"target": "box_99"},
                "result": {
                    "schema_version": "1.0",
                    "tool": "read_camera",
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "No object 'box_99' in the world",
                        "retryable": False,
                    },
                    "timestamp": "2026-10-03T09:16:00Z",
                },
            },
        ],
        "answer": "I don't know the color of box_99.\nStored evidence: none.\nObserved evidence: none.",
    },
}


# ---- HTTP server --------------------------------------------------------------------------

SESSION: LiveSession | None = None
# SQLite connections belong to the thread that created them, so the memory layer, the sensors and
# every agent run all live on this one worker thread. HTTP handler threads only queue jobs.
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-worker")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal readable
        return

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        assert SESSION is not None
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/api/state":
            self._json(
                {
                    "scenario": SESSION.scenario,
                    "replay": SESSION.replay,
                    "has_recording": SESSION.replay_trace is not None,
                    "frame": SESSION.initial_frame,
                    "error": SESSION.error,
                    "run": SESSION.run_no,
                    **SESSION.state.snapshot(),
                }
            )
        elif url.path == "/api/replay":
            if SESSION.replay_trace is None:
                self._json({"error": "no saved trace loaded"}, 404)
            else:
                self._json(SESSION.replay_trace)
        elif url.path == "/api/reset":
            scenario = (query.get("scenario") or [SESSION.scenario])[0]
            if SESSION.replay_trace is not None:
                self._json({"error": "the recorded scenario cannot be changed"}, 400)
            elif scenario not in SCENARIOS:
                self._json({"error": "unknown scenario"}, 400)
            elif not SESSION.busy.acquire(blocking=False):
                self._json({"error": "a question is still running"}, 409)
            else:
                try:
                    WORKER.submit(SESSION.reset, scenario).result()
                finally:
                    SESSION.busy.release()
                self._json(
                    {
                        "scenario": SESSION.scenario,
                        "replay": SESSION.replay,
                        "frame": SESSION.initial_frame,
                        "error": SESSION.error,
                        "run": 0,
                        **SESSION.state.snapshot(),
                    }
                )
        elif url.path == "/api/ask":
            if SESSION.replay_trace is not None:
                self._json({"error": "asking is disabled in saved replay mode"}, 405)
            else:
                self._stream_answer((query.get("q") or [""])[0].strip())
        else:
            self._static(url.path)

    def _static(self, path: str) -> None:
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (UI_DIR / name).resolve()
        if UI_DIR.resolve() not in target.parents or not target.is_file():
            self._json({"error": "not found"}, 404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_answer(self, question: str) -> None:
        assert SESSION is not None
        if not question:
            self._json({"error": "empty question"}, 400)
            return
        if not SESSION.busy.acquire(blocking=False):
            self._json({"error": "a question is still running"}, 409)
            return
        events: queue.Queue = queue.Queue()

        def work() -> None:
            try:
                SESSION.ask(question, events.put)
            except Exception as exc:
                traceback.print_exc()
                events.put(
                    {
                        "type": "final",
                        "answer": "",
                        "error": {"code": "INTERNAL", "message": str(exc)},
                    }
                )
            finally:
                events.put({"type": "done"})
                SESSION.busy.release()

        WORKER.submit(work)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                event = events.get()
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
                self.wfile.flush()
                if event.get("type") == "done":
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass


def load_trace(path: Path) -> dict[str, Any]:
    """Read the documented frame format and reject traces with no renderable frames."""
    def invalid_number(value: str) -> None:
        raise ValueError(f"non-JSON number {value}")

    trace = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_number)
    if not isinstance(trace, dict):
        raise ValueError("expected a JSON object")
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("expected a trace containing nonempty frames[]")
    previous = -1
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f"frame {index} must be an object")
        step = frame.get("step")
        if type(step) is not int or step <= previous or (index == 0 and step != 0):
            raise ValueError("frames must begin at step 0 and increase by step")
        world = frame.get("world")
        if not isinstance(world, dict) or not {
            "bounds_cm", "robot", "obstacles", "objects", "lighting", "sensors"
        } <= world.keys() or not isinstance(frame.get("beliefs"), list):
            raise ValueError(f"frame {step} is missing world or belief data")
        previous = step
    return trace


def main() -> None:
    global SESSION
    parser = argparse.ArgumentParser(
        description="Live demo UI for the I, Agent procedural layer"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", choices=SCENARIOS, default="scenario_a")
    parser.add_argument(
        "--replay", type=Path, nargs="?", const=Path("."),
        help="play a saved trace with frames, or omit the path for legacy playback",
    )
    args = parser.parse_args()
    replay_trace = None
    scenario = args.scenario
    if args.replay is not None and args.replay != Path("."):
        try:
            replay_trace = load_trace(args.replay)
        except (OSError, ValueError) as exc:
            parser.error(f"could not read replay: {exc}")
        scenario = replay_trace.get("scenario") or replay_trace["frames"][0]["world"].get("scenario") or scenario
    SESSION = WORKER.submit(LiveSession, scenario, args.replay is not None, replay_trace).result()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    mode = "REPLAY (recorded runs)" if args.replay else "LIVE (real model and layers)"
    print(f"I, Agent live UI: {mode}\nOpen http://127.0.0.1:{args.port}")
    if SESSION.error:
        print(f"Setup problem: {SESSION.error}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
