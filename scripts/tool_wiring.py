"""Connects the procedural layer to the other two layers: builds the tool registry.

This is the only place that imports declarative/ and sensorimotor/ (a composition root,
like evaluation/runner.py).

- Memory tools: Vyom's BeliefMemory (declarative/belief_graph.py) is created once per run and
  its methods are the five memory tools. Its methods already return ToolResult envelopes.
- Sensor and action tools: Asvin's simulated world (sensorimotor.create_sensorimotor) is created
  once per run and its tool_registry() supplies the six sensor and action tools. If it is
  missing, or does not provide a tool, the test fake in tests/procedural/fakes fills in.

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

SENSOR_TOOLS: tuple[str, ...] = (
    "read_lidar",
    "read_camera",
    "get_position",
    "move_forward",
    "move_backward",
    "turn",
)
SENSORIMOTOR_MODULE = "sensorimotor"
SENSORIMOTOR_SOURCE = "sensorimotor.Sensorimotor"
DEFAULT_SCENARIO = "scenario_a"
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


def build_sensorimotor(scenario: str = DEFAULT_SCENARIO, seed: int | None = None) -> Any | None:
    """Create Asvin's simulated world for one run.

    Returns None if sensorimotor/ does not provide create_sensorimotor yet. Raises RuntimeError
    if the scenario cannot be loaded (unknown name, invalid file).
    """
    module = _import_or_none(SENSORIMOTOR_MODULE)
    factory = getattr(module, "create_sensorimotor", None) if module is not None else None
    if factory is None:
        return None
    try:
        return factory(scenario, seed)
    except Exception as exc:
        raise RuntimeError(f"Could not start sensorimotor scenario {scenario!r}: {exc}") from exc


def build_tool_registry(
    use_real: bool = True,
    memory: Any | None = None,
    sensorimotor: Any | None = None,
    scenario: str = DEFAULT_SCENARIO,
    real_sensors: bool = True,
) -> tuple[dict[str, ToolFn], dict[str, str]]:
    """Build the registry for run_agent.

    Inputs: use_real=False forces the fakes (offline tests). memory and sensorimotor are
    existing layer objects to use instead of fresh ones (tests, Yash's runner). scenario
    names the sensorimotor world to build when none is passed. real_sensors=False keeps the
    real memory but uses the fake sensors (tests that must not depend on Asvin's layer).
    Outputs: (registry of tool name -> function, tool name -> "module" it came from).
    Raises RuntimeError if no implementation exists for a tool, or the scenario is invalid.
    """
    registry: dict[str, ToolFn] = {}
    sources: dict[str, str] = {}
    if use_real:
        memory = memory if memory is not None else build_memory()
        if memory is not None:
            for name in MEMORY_TOOLS:
                registry[name] = getattr(memory, name)
                sources[name] = MEMORY_SOURCE
        world = None
        if real_sensors:
            world = sensorimotor if sensorimotor is not None else build_sensorimotor(scenario)
        if world is not None:
            provided = world.tool_registry()
            for name in SENSOR_TOOLS:
                if name in provided:
                    registry[name] = provided[name]
                    sources[name] = SENSORIMOTOR_SOURCE
    for spec in TOOL_SPECS:
        if spec.name in registry:
            continue
        fake = FAKE_MEMORY_MODULE if spec.name in MEMORY_TOOLS else FAKE_SENSOR_MODULE
        fn = _load(fake, spec.name)
        if fn is None:
            raise RuntimeError(f"No implementation found for tool {spec.name}")
        registry[spec.name] = fn
        sources[spec.name] = fake
    fakes = sorted(n for n, m in sources.items() if m.startswith(FAKES_PACKAGE))
    logger.info("tools using fakes: %s", fakes or "none")
    return registry, sources
