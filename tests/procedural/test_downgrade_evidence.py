"""P5: a downgrade needs solid live evidence (D14, tests T04 and T05), plus the shared policy."""

from __future__ import annotations

import pytest

from procedural import update_guard
from procedural.update_guard import check_memory_call, distance_readings
from tests.procedural.test_checklist_enforcement import entry

BELIEF = {
    "belief_id": "b_000001",
    "subject": "path_A",
    "predicate": "status",
    "object": "clear",
    "confidence": 1.0,
    "perspective": "historical",
}
DOWNGRADE = {"belief_id": "b_000001", "new_confidence": 0.3, "reason": "live reading"}


def lidar(confidence: float = 0.98, status: str = "blocked", value: float = 12) -> dict:
    return {
        "sensor": "lidar_front",
        "unit": "cm",
        "value": value,
        "status": status,
        "confidence": confidence,
    }


def ultrasonic(confidence: float = 0.85, status: str = "blocked") -> dict:
    return {
        "sensor": "ultrasonic_front",
        "unit": "cm",
        "value": 15,
        "status": status,
        "confidence": confidence,
    }


def log(*readings: tuple[str, dict]) -> list[dict]:
    return [
        entry("query_belief", data=[BELIEF]),
        *(entry(t, data=d) for t, d in readings),
    ]


def test_strong_reading_allows_the_downgrade() -> None:
    d = check_memory_call("downgrade_belief", DOWNGRADE, log(("read_lidar", lidar())))
    assert d.error is None


def test_weak_reading_refuses_the_downgrade_t04() -> None:
    d = check_memory_call(
        "downgrade_belief", DOWNGRADE, log(("read_lidar", lidar(confidence=0.4)))
    )
    assert d.error and "0.4" in d.error and "0.6" in d.error
    assert "ask for a better reading" in d.error


def test_a_reading_exactly_at_the_minimum_is_strong_enough() -> None:
    d = check_memory_call(
        "downgrade_belief", DOWNGRADE, log(("read_lidar", lidar(confidence=0.6)))
    )
    assert d.error is None


def test_one_strong_sensor_is_enough_when_the_other_agrees() -> None:
    d = check_memory_call(
        "downgrade_belief",
        DOWNGRADE,
        log(("read_lidar", lidar(confidence=0.4)), ("read_ultrasonic", ultrasonic())),
    )
    assert d.error is None  # best reading is 0.85 and both say blocked


def test_disagreeing_distance_sensors_refuse_the_downgrade_t05() -> None:
    d = check_memory_call(
        "downgrade_belief",
        DOWNGRADE,
        log(
            ("read_lidar", lidar(0.98, "clear", 250)),
            ("read_ultrasonic", ultrasonic(0.85, "blocked")),
        ),
    )
    assert d.error and "disagree" in d.error and "disputed" in d.error
    assert "lidar_front says clear" in d.error
    assert "ultrasonic_front says blocked" in d.error


def test_agreeing_distance_sensors_do_not_block_the_downgrade() -> None:
    d = check_memory_call(
        "downgrade_belief",
        DOWNGRADE,
        log(("read_lidar", lidar()), ("read_ultrasonic", ultrasonic())),
    )
    assert d.error is None


def test_only_the_latest_reading_of_each_sensor_counts() -> None:
    old_then_new = log(
        ("read_lidar", lidar(0.98, "clear", 250)),
        ("read_ultrasonic", ultrasonic(0.85, "blocked")),
        ("read_lidar", lidar(0.98, "blocked", 14)),  # the world changed or a recheck
    )
    assert check_memory_call("downgrade_belief", DOWNGRADE, old_then_new).error is None


def test_no_distance_reading_yet_refuses_the_downgrade() -> None:
    d = check_memory_call("downgrade_belief", DOWNGRADE, log())
    assert d.error and "no distance sensor has been read" in d.error
    assert "read_lidar" in d.error


def test_camera_and_position_are_not_distance_sensors() -> None:
    camera = {
        "sensor": "camera_front",
        "unit": None,
        "status": "observed",
        "confidence": 0.3,
    }
    pos = {"sensor": "position", "unit": None, "status": "clear", "confidence": 1.0}
    entries = log(("read_camera", camera), ("get_position", pos))
    assert distance_readings(entries) == {}
    # a camera or position read is not evidence about distance, so the downgrade is refused
    error = check_memory_call("downgrade_belief", DOWNGRADE, entries).error
    assert error and "no distance sensor" in error


def test_a_failed_sensor_read_does_not_count() -> None:
    entries = log(("read_lidar", lidar()))
    entries.append(entry("read_ultrasonic", ok=False, code="TIMEOUT"))
    assert check_memory_call("downgrade_belief", DOWNGRADE, entries).error is None


def test_refusals_do_not_touch_sensor_updates_or_other_tools() -> None:
    entries = log(("read_lidar", lidar(0.4)))
    update = {
        "subject": "path_A",
        "predicate": "status",
        "object": "blocked",
        "source": "lidar_front",
        "confidence": 0.4,
        "perspective": "agent_sensor",
        "reason": "live reading",
    }
    assert (
        check_memory_call("update_belief", update, entries, ("path_A",)).error is None
    )


def test_ultrasonic_reads_are_recognised_as_sensor_reads() -> None:
    assert "read_ultrasonic" in update_guard.SENSOR_READ_TOOLS


def test_thresholds_match_the_shared_policy_when_it_exists() -> None:
    policy = pytest.importorskip("contracts.policy")
    assert update_guard.DOWNGRADE_FACTOR == policy.DOWNGRADE_FACTOR
    assert update_guard.LIVE_SENSOR_MIN == policy.LIVE_SENSOR_MIN
    assert update_guard.USER_INPUT_CONFIDENCE == policy.USER_STATEMENT_CONF


def test_fallback_thresholds_equal_the_agreed_policy_numbers() -> None:
    assert update_guard.DOWNGRADE_FACTOR == 0.3
    assert update_guard.LIVE_SENSOR_MIN == 0.6
    assert update_guard.USER_INPUT_CONFIDENCE == 0.9


def test_reading_that_confirms_the_belief_refuses_the_downgrade() -> None:
    """The map says clear, the LiDAR says clear: memory is confirmed, nothing to downgrade."""
    d = check_memory_call(
        "downgrade_belief", DOWNGRADE, log(("read_lidar", lidar(0.98, "clear", 250)))
    )
    assert d.error and "agrees with the stored belief" in d.error
    assert "path_A status is clear" in d.error and "unchanged" in d.error


def test_both_sensors_confirming_the_belief_also_refuse() -> None:
    d = check_memory_call(
        "downgrade_belief",
        DOWNGRADE,
        log(
            ("read_lidar", lidar(0.98, "clear", 250)),
            ("read_ultrasonic", ultrasonic(0.85, "clear")),
        ),
    )
    assert d.error and "agrees with the stored belief" in d.error


def test_a_reading_that_contradicts_the_belief_allows_the_downgrade() -> None:
    d = check_memory_call("downgrade_belief", DOWNGRADE, log(("read_lidar", lidar())))
    assert d.error is None  # belief says clear, LiDAR says blocked


def test_beliefs_that_are_not_a_status_are_not_compared() -> None:
    belief = {**BELIEF, "predicate": "colour", "object": "brown"}
    entries = [
        entry("query_belief", data=[belief]),
        entry("read_lidar", data=lidar(0.98, "clear", 250)),
    ]
    assert check_memory_call("downgrade_belief", DOWNGRADE, entries).error is None


def test_real_scenario_a_order_is_accepted() -> None:
    import json
    from pathlib import Path

    runs = json.loads(
        (Path(__file__).parent / "fixtures" / "scenario_a_runs.json").read_text()
    )
    calls = runs["tool_calls"]
    first_downgrade = next(
        i for i, c in enumerate(calls) if c["tool"] == "downgrade_belief"
    )
    before = calls[:first_downgrade]
    d = check_memory_call("downgrade_belief", calls[first_downgrade]["args"], before)
    assert d.error is None
