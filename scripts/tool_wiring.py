"""Connects the procedural layer to the other two layers: builds the tool registry.

This is the only place that imports declarative/ and sensorimotor/ (a composition root,
like evaluation/runner.py).

- Memory tools: Vyom's BeliefMemory (declarative/belief_graph.py) is created once per run and
  its methods are the five memory tools. Its methods already return ToolResult envelopes.
- Sensor and action tools: the real module is used when it exists, otherwise the test fake in
  tests/procedural/fakes fills in. Asvin's code is not on main yet.

The sources are logged so you can see which implementation is in use.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from procedural.tools import TOOL_SPECS, ToolFn

logger = logging.getLogger(__name__)

MEMORY_TOOLS: tuple[str, ...] = (
    "query_belief",
    "get_belief_history",
    "update_belief",
    "downgrade_belief",
    "detect_conflict",
)
MEMORY_MODULE = "declarative.belief_graph"
MEMORY_SOURCE = f"{MEMORY_MODULE}.BeliefMemory"

# Where Asvin's tools are expected to live. Edit these names when his code lands on main.
SENSOR_MODULES: dict[str, str] = {
    "read_lidar": "sensorimotor.sensors",
    "read_camera": "sensorimotor.sensors",
    "get_position": "sensorimotor.sensors",
    "move_forward": "sensorimotor.actions",
    "move_backward": "sensorimotor.actions",
    "turn": "sensorimotor.actions",
}
DEMO_TS = "2026-10-03T09:15:00Z"  # when the demo beliefs were stored, before the live reading
FAKES_PACKAGE = "tests.procedural.fakes"
FAKE_MEMORY_MODULE = f"{FAKES_PACKAGE}.declarative_fake"
FAKE_SENSOR_MODULE = f"{FAKES_PACKAGE}.sensorimotor_fake"


def _import_or_none(module_name: str) -> Any | None:
    """Return the module, or None if that module itself does not exist yet."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name is not None and module_name.startswith(exc.name):
            return None  # the module itself is missing; a missing dependency is a real bug
        raise


def _load(module_name: str, tool: str) -> ToolFn | None:
    """Return module.tool, or None if the module or the function does not exist yet."""
    module = _import_or_none(module_name)
    return None if module is None else getattr(module, tool, None)


def seed_demo_world(memory: Any) -> None:
    """Load the demo beliefs for manual runs (ask_agent.py): Scenario A and the box_01 case.

    path_A/status is "clear" from default_map (historical, 1.0). box_01/color has the user's
    belief "red" (0.9) and a third-party belief "blue" (0.8, bot_02). This is demo data for
    live runs, the same facts the evaluation scenarios use, not an implementation of memory.
    """
    from declarative.seed import seed_bot_02_record

    memory.add_belief("path_A", "status", "clear", "default_map", 1.0, "historical", DEMO_TS)
    memory.add_belief("box_01", "color", "red", "user", 0.9, "user", DEMO_TS)
    seed_bot_02_record(memory, "box_01", "color", "blue", 0.8, DEMO_TS)


def build_memory(seed: bool = True) -> Any | None:
    """Create Vyom's BeliefMemory (in-memory SQLite) and optionally seed it.

    Returns None if declarative/belief_graph.py does not exist yet.
    """
    module = _import_or_none(MEMORY_MODULE)
    if module is None:
        return None
    memory = module.BeliefMemory()
    if seed:
        seed_demo_world(memory)
    return memory


def build_tool_registry(
    use_real: bool = True, memory: Any | None = None
) -> tuple[dict[str, ToolFn], dict[str, str]]:
    """Build the registry for run_agent.

    Inputs: use_real=False forces the fakes (offline tests). memory is an existing
    BeliefMemory to use instead of a freshly seeded one (tests, Yash's runner).
    Outputs: (registry of tool name -> function, tool name -> "module" it came from).
    Raises RuntimeError if neither the real module nor the fake provides a tool.
    """
    registry: dict[str, ToolFn] = {}
    sources: dict[str, str] = {}
    if use_real:
        memory = memory if memory is not None else build_memory()
        if memory is not None:
            for name in MEMORY_TOOLS:
                registry[name] = getattr(memory, name)
                sources[name] = MEMORY_SOURCE
    for spec in TOOL_SPECS:
        if spec.name in registry:
            continue
        is_memory = spec.name in MEMORY_TOOLS
        real = [] if (is_memory or not use_real) else [SENSOR_MODULES[spec.name]]
        fake = FAKE_MEMORY_MODULE if is_memory else FAKE_SENSOR_MODULE
        for module_name in [*real, fake]:
            fn = _load(module_name, spec.name)
            if fn is not None:
                registry[spec.name] = fn
                sources[spec.name] = module_name
                break
        else:
            raise RuntimeError(f"No implementation found for tool {spec.name}")
    fakes = sorted(n for n, m in sources.items() if m.startswith(FAKES_PACKAGE))
    logger.info("tools using fakes: %s", fakes or "none")
    return registry, sources
