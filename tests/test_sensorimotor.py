"""Unit tests for the sensorimotor layer and the sensor-to-belief adapter.

Run from the repo root:  python -m pytest tests/test_sensorimotor.py
Checks the role's Definition of Done: valid contract JSON, state changes affect
later readings, deterministic reset from a seed, mid-run world change.
"""

import copy
import json

import pytest

from adapters.sensor_to_belief import reading_to_evidence
from sensorimotor import ScenarioConfigError, create_sensorimotor, load_scenario
from sensorimotor import _boundary as bd


def data(result):
    """Envelope dict -> validated SensorReading (fails the test if ok is false)."""
    assert isinstance(result, dict) and result["ok"], result.get("error")
    return bd.SensorReading.model_validate(result["data"])


# ------------------------------------------------------------ Scenario A / B
def test_scenario_a_lidar_blocked_at_12cm():
    r = data(create_sensorimotor("scenario_a").sensors.read_lidar())
    assert (r.sensor, r.value, r.unit, r.status) == ("lidar_front", 12, "cm", "blocked")


def test_scenario_b_camera_brown_under_yellow_light():
    r = data(create_sensorimotor("scenario_b").sensors.read_camera())
    assert r.value == {"object_id": "box_01", "color": "brown"}


def test_lighting_change_changes_camera():
    sm = create_sensorimotor("scenario_b")
    sm.env.apply_change({"type": "set_lighting", "lighting": {"name": "white", "color_shift": {}}})
    assert data(sm.sensors.read_camera("box_01")).value["color"] == "red"


# --------------------------------------------- state changes affect readings
def test_turning_changes_lidar():
    sm = create_sensorimotor("scenario_a")
    sm.actions.turn(90)
    assert data(sm.sensors.read_lidar()).status == "clear"


def test_moving_changes_lidar_and_position():
    sm = create_sensorimotor("scenario_b")
    before = data(sm.sensors.read_lidar()).value
    data(sm.actions.move_forward(10))
    assert data(sm.sensors.get_position()).value["x"] == 10
    assert data(sm.sensors.read_lidar()).value == before  # empty world: unchanged range


def test_move_stops_at_obstacle_and_reports_blocked():
    sm = create_sensorimotor("scenario_a")
    r = data(sm.actions.move_forward(100))
    assert r.status == "blocked" and r.value["x"] == 11  # 12 cm minus 1 cm margin


def test_move_backward_reverses():
    sm = create_sensorimotor("scenario_b")
    sm.actions.move_forward(20)
    assert data(sm.actions.move_backward(5)).value["x"] == 15


# ------------------------------------------------------- determinism / reset
def test_reset_restores_exact_state():
    sm = create_sensorimotor("scenario_a", seed=7)
    start = sm.env.get_state()
    sm.actions.turn(45)
    sm.actions.move_backward(30)
    sm.env.advance_time(60)
    sm.env.reset()
    assert sm.env.get_state() == start


def test_same_seed_same_readings_with_noise():
    raw = json.loads(
        json.dumps(
            {
                "name": "noisy",
                "robot": {"x": 0, "y": 0, "heading_deg": 0},
                "obstacles": [
                    {"obstacle_id": "w", "x_min": 100, "y_min": -5, "x_max": 110, "y_max": 5}
                ],
                "sensors": {
                    "lidar": [{"name": "lidar_front", "direction": "front", "noise_std_cm": 2.0}]
                },
            }
        )
    )

    def run(seed):
        sm = create_sensorimotor(raw, seed)
        return [data(sm.sensors.read_lidar()).value for _ in range(3)] + [
            data(sm.actions.turn(0.0)) and data(sm.sensors.read_lidar()).value
        ]

    assert run(5) == run(5)
    assert run(5) != run(6)


def test_reads_do_not_advance_time_actions_do():
    sm = create_sensorimotor("scenario_a")
    t0 = sm.env.now_iso()
    sm.sensors.read_lidar()
    assert sm.env.now_iso() == t0
    sm.actions.turn(10)
    assert sm.env.now_iso() != t0


# ----------------------------------------------------------- world change hook
def test_scheduled_world_change_mid_run():
    cfg = copy.deepcopy(load_scenario("scenario_b").__dict__)  # prove config is readable
    assert cfg["name"] == "scenario_b"
    sm = create_sensorimotor(
        {
            "name": "t10",
            "robot": {"x": 0, "y": 0, "heading_deg": 0},
            "sensors": {"lidar": [{"name": "lidar_front", "direction": "front"}]},
            "events": [
                {
                    "at_step": 2,
                    "change": {
                        "type": "add_obstacle",
                        "obstacle": {
                            "obstacle_id": "late",
                            "x_min": 50,
                            "y_min": -5,
                            "x_max": 60,
                            "y_max": 5,
                        },
                    },
                }
            ],
        }
    )
    assert data(sm.sensors.read_lidar()).status == "clear"
    sm.actions.turn(1)
    assert data(sm.sensors.read_lidar()).status == "clear"
    sm.actions.turn(-1)  # step 2 reached: obstacle appears
    assert data(sm.sensors.read_lidar()).value == 50
    sm.env.reset()  # reset removes the change again
    assert data(sm.sensors.read_lidar()).status == "clear"


# ---------------------------------------------------------- error envelopes
@pytest.mark.parametrize("bad", [0, -5, 10_000, "10", None, True, float("nan")])
def test_move_rejects_bad_distance(bad):
    res = create_sensorimotor().actions.move_forward(bad)
    assert not res["ok"] and res["error"]["code"] == "INVALID_ARGUMENT"


def test_turn_rejects_bad_degrees():
    sm = create_sensorimotor()
    assert sm.actions.turn(400)["error"]["code"] == "INVALID_ARGUMENT"
    assert sm.actions.turn("x")["error"]["code"] == "INVALID_ARGUMENT"


def test_lidar_bad_and_missing_direction():
    sm = create_sensorimotor()
    assert sm.sensors.read_lidar("up")["error"]["code"] == "INVALID_ARGUMENT"
    assert sm.sensors.read_lidar("back")["error"]["code"] == "SENSOR_UNAVAILABLE"


def test_camera_unknown_target_not_found():
    assert (
        create_sensorimotor("scenario_b").sensors.read_camera("ghost")["error"]["code"]
        == "NOT_FOUND"
    )


def test_unavailable_sensor_gives_error_and_no_action():
    sm = create_sensorimotor(
        {
            "name": "outage",
            "robot": {"x": 0, "y": 0, "heading_deg": 0},
            "sensors": {
                "lidar": [{"name": "lidar_front", "direction": "front", "available": False}],
                "position": {"available": False},
            },
        }
    )
    assert sm.sensors.read_lidar()["error"]["code"] == "SENSOR_UNAVAILABLE"
    assert sm.actions.move_forward(5)["error"]["code"] == "SENSOR_UNAVAILABLE"
    assert sm.env.pose["x"] == 0  # action was not executed


def test_camera_sees_nothing_gives_unknown():
    sm = create_sensorimotor("scenario_b")
    sm.actions.turn(180)
    r = data(sm.sensors.read_camera())
    assert r.status == "unknown" and r.value == {"object_id": None, "color": None}


# ------------------------------------------------------------ contract checks
def test_every_output_validates_and_is_json():
    sm = create_sensorimotor("scenario_b")
    results = [
        sm.sensors.read_lidar(),
        sm.sensors.read_camera(),
        sm.sensors.get_position(),
        sm.actions.move_forward(5),
        sm.actions.move_backward(2),
        sm.actions.turn(10),
        sm.sensors.read_lidar("up"),
        sm.actions.move_forward(-1),
    ]
    for res in results:
        dumped = res
        assert isinstance(res, dict)
        json.dumps(dumped)
        assert bd.ToolResult.model_validate(dumped)
        assert dumped["schema_version"] == "1.0" and dumped["timestamp"].endswith("Z")
        assert dumped["ok"] == (dumped["error"] is None)


def test_no_exception_escapes_on_unexpected_failure(monkeypatch):
    sm = create_sensorimotor()
    monkeypatch.setattr(sm.env, "ray_distance", lambda *a, **k: 1 / 0)
    res = sm.sensors.read_lidar()
    assert not res["ok"] and res["error"]["code"] == "INTERNAL"


def test_bad_scenario_rejected_at_setup():
    with pytest.raises(ScenarioConfigError):
        load_scenario({"name": "x"})  # no robot
    with pytest.raises(ScenarioConfigError):
        load_scenario("does_not_exist")


def test_registry_exposes_all_tools_returning_dicts():
    sm = create_sensorimotor("scenario_a")
    reg = sm.tool_registry()
    assert set(reg) == {
        "read_lidar",
        "read_camera",
        "get_position",
        "move_forward",
        "move_backward",
        "turn",
    }
    assert reg["read_lidar"](direction="front")["data"]["value"] == 12
    assert reg["turn"](degrees=90)["ok"]


def test_boundary_unknown_error_code_becomes_internal():
    res = bd.failure("t", "MADE_UP", "nope", False, "2026-10-03T09:00:00Z")  # model-level helper
    assert res.error.code == "INTERNAL"


# -------------------------------------------------------------------- adapter
def test_adapter_lidar_blocked():
    ev = reading_to_evidence(data(create_sensorimotor("scenario_a").sensors.read_lidar()))
    assert (ev.subject, ev.predicate, ev.object) == ("path_A", "status", "blocked")
    assert (ev.source, ev.confidence, ev.perspective) == ("lidar_front", 0.98, "agent_sensor")


def test_adapter_camera_and_dict_input():
    ev = reading_to_evidence(data(create_sensorimotor("scenario_b").sensors.read_camera()))
    assert (ev.subject, ev.predicate, ev.object) == ("box_01", "color", "brown")
    as_dict = {
        "sensor": "lidar_front",
        "value": 400,
        "unit": "cm",
        "status": "clear",
        "timestamp": "2026-10-03T09:00:00Z",
        "confidence": 0.98,
    }
    assert reading_to_evidence(as_dict).object == "clear"


def test_adapter_returns_none_without_evidence():
    sm = create_sensorimotor("scenario_b")
    sm.actions.turn(180)
    assert reading_to_evidence(data(sm.sensors.read_camera())) is None
    assert reading_to_evidence(data(sm.sensors.get_position())) is None


def test_adapter_accepts_tool_envelope_and_failed_envelope():
    sm = create_sensorimotor("scenario_a")
    ev = reading_to_evidence(sm.sensors.read_lidar())  # whole envelope dict
    assert (ev.subject, ev.object) == ("path_A", "blocked")
    assert reading_to_evidence(sm.sensors.read_lidar("up")) is None  # ok=false


@pytest.mark.parametrize(
    "bad",
    [
        {"confidence": 1.5},
        {"confidence": "0.9"},
        {"confidence": True},
        {"perspective": "robot"},
        {"source": None},
        {"subject": ""},
        {"object": None},
        {"object": ["x"]},
    ],
)
def test_adapter_output_is_validated(bad):
    from adapters.sensor_to_belief import BeliefEvidence

    good = dict(
        subject="path_A",
        predicate="status",
        object="blocked",
        source="lidar_front",
        confidence=0.98,
        perspective="agent_sensor",
        reason="r",
    )
    assert BeliefEvidence(**good)
    with pytest.raises(ValueError):
        BeliefEvidence(**{**good, **bad})
