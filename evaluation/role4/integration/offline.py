"""Process-local network/dotenv protection; no credential values are read or recorded."""
import os
import socket
import argparse
from pathlib import Path
import runpy
import sys
from contextlib import contextmanager
from unittest.mock import patch
from functools import partial


@contextmanager
def offline_guard():
    """Remove inherited API keys, disable dotenv loading, and reject all socket connects/DNS."""
    blocked_attempts = []

    def reject(*args, **kwargs):
        blocked_attempts.append("network_attempt")
        raise RuntimeError("Role 4 offline guard: network access prohibited")

    clean = {k: v for k, v in os.environ.items() if not k.endswith("API_KEY")}
    clean.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    with patch.dict(os.environ, clean, clear=True), \
            patch.object(socket.socket, "connect", reject), \
            patch.object(socket.socket, "connect_ex", reject), \
            patch.object(socket, "create_connection", reject), \
            patch.object(socket, "getaddrinfo", reject):
        try:
            import dotenv
        except ImportError:
            yield blocked_attempts
        else:
            with patch.object(dotenv, "load_dotenv", return_value=False), \
                    patch.object(dotenv, "dotenv_values", return_value={}):
                yield blocked_attempts


def main():
    """Guard existing Role 4 reference demos without altering their historical source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Fresh destination for the older Phase 1/2 demos' fixed output paths")
    parser.add_argument("script", choices=("run_role4_phase1_demo.py", "run_role4_phase2_demo.py",
                                         "run_role4_phase3_demo.py", "run_role4_midproject.py"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    target = root / "scripts" / args.script
    sys.argv = [str(target)] + args.arguments
    with offline_guard():
        if args.output_dir is None:
            runpy.run_path(str(target), run_name="__main__")
        else:
            if args.script not in ("run_role4_phase1_demo.py", "run_role4_phase2_demo.py"):
                parser.error("For Phase 3/five-case demos pass their native --output-dir after the script name")
            destination = args.output_dir.resolve()
            destination.mkdir(parents=True, exist_ok=False)
            namespace = runpy.run_path(str(target))
            # Redirect only output I/O; source fixtures and evaluation functions remain unchanged.
            phase = "phase1" if args.script == "run_role4_phase1_demo.py" else "phase2"
            prefix = root / "evaluation/logs/role4" / phase
            def route(path):
                return destination / Path(path).relative_to(prefix)
            from evaluation.role4.logger import EventLogger, read_events, write_json
            replacement = {"write_json": lambda p, d: write_json(route(p), d)}
            if phase == "phase1":
                replacement.update(EventLogger=lambda p: EventLogger(route(p)), read_events=lambda p: read_events(route(p)))
            else:
                replacement["run_s01"] = partial(namespace["run_s01"], output_dir=destination)
            with patch.dict(namespace["main"].__globals__, replacement):
                raise SystemExit(namespace["main"]())


if __name__ == "__main__":
    main()
