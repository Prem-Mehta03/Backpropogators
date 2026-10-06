"""Run offline pytest with explicit hosted exclusions, dotenv protection and socket denial."""
import argparse
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from evaluation.role4.integration.offline import offline_guard


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-path", type=Path, help="Optional existing compatible pure-Python dependency directory; no installation")
    parser.add_argument("--suite", choices=("role4", "teammate", "full"), default="full")
    args = parser.parse_args(argv)
    if args.dependency_path:
        if not args.dependency_path.is_dir():
            parser.error("Dependency directory unavailable")
        sys.path.append(str(args.dependency_path.resolve()))
    with offline_guard() as blocked:
        import pytest
        for name in ("pydantic", "networkx", "pytest"):
            module = importlib.import_module(name)
            print("dependency", name, getattr(module, "__version__", "unknown"), module.__file__)
        target = ["tests/role4"] if args.suite == "role4" else ["tests", "--ignore=tests/role4"] if args.suite == "teammate" else ["tests"]
        exclusions = ["--ignore=tests/procedural/test_agent_live.py",
                      "--deselect=tests/procedural/test_single_tool_call.py::test_live_model_calls_read_lidar"]
        print("Explicit offline exclusions:", exclusions)
        code = pytest.main(target + exclusions + ["-p", "no:cacheprovider", "--continue-on-collection-errors", "--tb=short", "-q"])
    print("Blocked network attempts:", len(blocked))
    return int(code) if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
