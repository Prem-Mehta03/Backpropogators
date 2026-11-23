"""Sample all registered teammate tools against their canonical return types."""

from pathlib import Path

from contracts.models import Belief, SensorReading, ToolResult
from evaluation.role4.integration.teammate_runner import require_real_tools, verify_imports
from evaluation.role4.logger import write_json

LIST_TOOLS = {"query_belief", "get_belief_history", "detect_conflict"}
BELIEF_TOOLS = {"update_belief", "downgrade_belief"}


def validate_tool_output(tool: str, raw: dict) -> None:
    """Validate the envelope name and successful payload. Raise ValueError on a mismatch."""
    result = ToolResult.model_validate(raw)
    if result.tool != tool:
        raise ValueError(f"Expected envelope for {tool}, received {result.tool}")
    if not result.ok:
        return
    if tool in LIST_TOOLS:
        if not isinstance(result.data, list):
            raise ValueError(f"{tool} requires a list of beliefs")
        for belief in result.data:
            Belief.model_validate(belief)
    elif tool in BELIEF_TOOLS:
        Belief.model_validate(result.data)
    else:
        SensorReading.model_validate(result.data)


def probe_registry(output: Path, seed: int) -> dict:
    """Call all 11 actual tools in an isolated simulation and write sample validation receipts."""
    from declarative import BeliefMemory
    from scripts.tool_wiring import MEMORY_TOOLS, SENSOR_TOOLS, build_tool_registry
    from sensorimotor import create_sensorimotor

    verify_imports()
    world = create_sensorimotor("scenario_b", seed)
    memory = BeliefMemory(clock=world.env.now_iso)
    rows = []
    try:
        registry, sources = build_tool_registry(memory=memory, sensorimotor=world)
        require_real_tools(registry, sources, memory, world)
        query = {"subject": "box_01", "predicate": "color"}
        memory.add_belief("box_01", "color", "red", "user", 0.9, "user", "2026-10-03T09:15:00Z")
        map_seed = memory.add_belief(
            "path_A", "status", "clear", "default_map", 1.0, "historical", "2026-10-03T09:15:00Z"
        )

        def probe(tool: str, arguments: dict, expected_ok: bool = True) -> dict:
            raw = registry[tool](**arguments)
            error = None
            try:
                validate_tool_output(tool, raw)
                if raw["ok"] != expected_ok:
                    error = f"Expected ok={expected_ok}"
            except ValueError as exc:
                error = str(exc)
            rows.append({"tool": tool, "source": sources[tool], "arguments": arguments,
                         "result": raw, "expected_ok": expected_ok, "passed": error is None,
                         "error": error, "layer": "declarative" if tool in MEMORY_TOOLS else "sensorimotor"})
            return raw

        probe("query_belief", query)
        probe("get_belief_history", query)
        probe("detect_conflict", query)
        probe("read_lidar", {"direction": "front"})
        probe("read_camera", {"target": "box_01"})
        probe("get_position", {})
        probe("move_forward", {"distance_cm": 1})
        probe("move_backward", {"distance_cm": 1})
        probe("turn", {"degrees": 10})
        probe("update_belief", {**query, "object": "red", "source": "user", "confidence": 0.9,
                                        "perspective": "user", "reason": "contract probe"})
        probe("downgrade_belief", {"belief_id": map_seed["data"]["belief_id"], "new_confidence": 0.4,
                                   "reason": "contract probe"})
        probe("downgrade_belief", {"belief_id": "b_999999", "new_confidence": 0.4, "reason": "contract probe"}, False)
        probe("query_belief", {"subject": ""}, False)
        probe("read_lidar", {"direction": "invalid"}, False)
        assert {row["tool"] for row in rows} == set(MEMORY_TOOLS + SENSOR_TOOLS)
    finally:
        memory.close()
    data = {"scope": "direct teammate tool boundary samples in a simulated Scenario B",
            "seed": seed, "distinct_tools": len({row["tool"] for row in rows}), "samples": rows,
            "passed": all(row["passed"] for row in rows)}
    write_json(output, data)
    return data
