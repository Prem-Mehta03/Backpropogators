"""Registry wiring: stubs by default, real modules picked up automatically when they exist."""

from __future__ import annotations

import sys
import types

import pytest

from procedural.tools import registered_tool_schemas
from scripts.tool_wiring import SENSORIMOTOR_SOURCE, build_tool_registry


def test_stubs_only_registry_has_all_eleven_tools() -> None:
    registry, sources = build_tool_registry(use_real=False)
    assert len(registry) == 11
    assert set(sources.values()) == {
        "tests.procedural.fakes.declarative_fake",
        "tests.procedural.fakes.sensorimotor_fake",
    }
    assert "read_ultrasonic" not in {
        schema["function"]["name"] for schema in registered_tool_schemas(registry)
    }


def test_ultrasonic_is_only_advertised_when_the_world_registers_it() -> None:
    def read_ultrasonic() -> dict:
        return {}

    class World:
        def tool_registry(self) -> dict:
            return {"read_ultrasonic": read_ultrasonic}

    registry, sources = build_tool_registry(sensorimotor=World())
    assert len(registry) == 12 and registry["read_ultrasonic"] is read_ultrasonic
    assert sources["read_ultrasonic"] == SENSORIMOTOR_SOURCE
    offered = {schema["function"]["name"] for schema in registered_tool_schemas(registry)}
    assert offered == set(registry)


def test_real_sensorimotor_world_is_preferred_when_it_provides_the_tool() -> None:
    marker = object()

    class World:
        def tool_registry(self) -> dict[str, object]:
            return {"read_lidar": marker}

    registry, sources = build_tool_registry(sensorimotor=World())
    assert (
        registry["read_lidar"] is marker
        and sources["read_lidar"] == SENSORIMOTOR_SOURCE
    )
    # tools the world does not provide are filled in by the fake, and logged as such
    assert sources["read_camera"] == "tests.procedural.fakes.sensorimotor_fake"


def test_missing_sensorimotor_factory_falls_back_to_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sensorimotor", types.ModuleType("sensorimotor"))
    _, sources = build_tool_registry()
    for name in ("read_lidar", "read_camera", "get_position", "move_forward", "turn"):
        assert sources[name].startswith("tests.procedural.fakes")


def test_bad_scenario_raises_runtime_error_with_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(scenario: str, seed: int | None = None) -> None:
        raise ValueError("no such scenario")

    module = types.ModuleType("sensorimotor")
    module.create_sensorimotor = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sensorimotor", module)
    with pytest.raises(RuntimeError, match="scenario_z"):
        build_tool_registry(scenario="scenario_z")


def test_real_sensors_can_be_switched_off() -> None:
    class World:
        def tool_registry(self) -> dict[str, object]:
            return {"read_lidar": object()}

    _, sources = build_tool_registry(sensorimotor=World(), real_sensors=False)
    assert sources["read_lidar"] == "tests.procedural.fakes.sensorimotor_fake"
