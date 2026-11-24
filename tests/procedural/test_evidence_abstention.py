"""Scoped abstention may proceed without guessing facts or bypassing evidence rules."""

import pytest

from contracts.validators import success_result
from procedural.agent import run_agent
from procedural.checklist import EvidenceCapability
from procedural.prompts import ABSTENTION_SIGNAL
from procedural.tools import error_result
from tests.procedural.scripted_llm import ScriptedLLM, call, say

STAMP = "2026-10-03T09:16:00Z"
BATTERY = EvidenceCapability(
    "robot", "battery_percent", "read_battery", "battery level"
)
CAMERA = EvidenceCapability(
    "box_99", "color", "read_camera", "box color", (("target", "box_99"),)
)


def _empty_read(subject: str, predicate: str | None = None):
    return error_result("query_belief", "NOT_FOUND", "No recorded belief.")


def _model(*turns):
    return ScriptedLLM(list(turns))


def test_confirmed_absent_sensor_allows_an_explicit_bounded_response():
    llm = _model(call("query_belief", {"subject": "robot"}), say(ABSTENTION_SIGNAL))
    result = run_agent(
        "Battery level?",
        llm,
        {"query_belief": _empty_read},
        max_steps=2,
        evidence_capability=BATTERY,
    )
    assert result.finished
    assert result.answer_source == "fallback_summary"
    assert "No matching sensor is connected." in result.answer
    assert "Memory returned no matching claim." in result.answer


@pytest.mark.parametrize(
    "incompatible_args",
    [
        {"subject": "other"},
        {"subject": "robot", "predicate": "color"},
        {"subject": "robot", "perspective": "historical"},
    ],
)
def test_an_unrelated_or_restricted_lookup_cannot_unlock_abstention(incompatible_args):
    llm = _model(call("query_belief", incompatible_args), say(ABSTENTION_SIGNAL))
    result = run_agent(
        "Battery level?",
        llm,
        {"query_belief": _empty_read},
        max_steps=2,
        evidence_capability=BATTERY,
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer


@pytest.mark.parametrize("tool_code", ["INVALID_ARGUMENT", "INTERNAL", "STORAGE_ERROR"])
def test_wrong_sensor_errors_do_not_unlock_abstention(tool_code):
    llm = _model(
        call("query_belief", {"subject": "box_99"}),
        call("read_camera", {"target": "box_99"}),
        say(ABSTENTION_SIGNAL),
    )
    registry = {
        "query_belief": _empty_read,
        "read_camera": lambda target: error_result(
            "read_camera", tool_code, "sensor failed"
        ),
    }
    result = run_agent(
        "Box color?", llm, registry, max_steps=3, evidence_capability=CAMERA
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer


def test_unavailable_sensor_must_match_the_requested_target():
    llm = _model(
        call("query_belief", {"subject": "box_99"}),
        call("read_camera", {"target": "box_01"}),
        say(ABSTENTION_SIGNAL),
    )
    registry = {"query_belief": _empty_read, "read_camera": _unavailable_camera}
    result = run_agent(
        "Box color?", llm, registry, max_steps=3, evidence_capability=CAMERA
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer


def test_unrelated_unavailability_does_not_satisfy_a_registered_capability():
    llm = _model(
        call("query_belief", {"subject": "box_99"}),
        call("read_lidar"),
        say(ABSTENTION_SIGNAL),
    )
    registry = {
        "query_belief": _empty_read,
        "read_camera": _unavailable_camera,
        "read_lidar": lambda: error_result(
            "read_lidar", "SENSOR_UNAVAILABLE", "No distance reading."
        ),
    }
    result = run_agent(
        "Box color?", llm, registry, max_steps=3, evidence_capability=CAMERA
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer


def _unavailable_camera(target: str):
    return error_result("read_camera", "SENSOR_UNAVAILABLE", f"No image of {target}.")


def test_registered_unavailable_sensor_accepts_abstention_and_rejects_appended_fact():
    false_answer = f"{ABSTENTION_SIGNAL} The box is definitely red."
    llm = _model(
        call("query_belief", {"subject": "box_99"}),
        call("read_camera", {"target": "box_99"}),
        say(false_answer),
        say(ABSTENTION_SIGNAL),
    )
    registry = {"query_belief": _empty_read, "read_camera": _unavailable_camera}
    result = run_agent(
        "Box color?", llm, registry, max_steps=4, evidence_capability=CAMERA
    )
    assert result.finished and result.evidence_nudges == 1
    assert result.answer_source == "fallback_summary"
    assert "matching sensor returned no usable evidence" in result.answer
    assert "red" not in result.answer


def test_absent_sensor_cannot_unlock_a_positive_answer():
    llm = _model(
        call("query_belief", {"subject": "robot"}),
        say(f"{ABSTENTION_SIGNAL} The battery is at eighty percent."),
    )
    result = run_agent(
        "Battery level?",
        llm,
        {"query_belief": _empty_read},
        max_steps=2,
        evidence_capability=BATTERY,
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer


def test_scope_with_usable_sensor_keeps_the_normal_answer_path():
    def read_camera(target):
        return success_result(
            "read_camera",
            {
                "schema_version": "1.1",
                "sensor": "camera_front",
                "value": {"object_id": target, "color": "red"},
                "unit": None,
                "status": "clear",
                "timestamp": STAMP,
                "confidence": 0.9,
            },
            STAMP,
        )

    llm = _model(
        call("query_belief", {"subject": "box_99"}),
        call("read_camera", {"target": "box_99"}),
        say("The camera observed red."),
    )
    registry = {"query_belief": _empty_read, "read_camera": read_camera}
    result = run_agent(
        "Box color?", llm, registry, max_steps=3, evidence_capability=CAMERA
    )
    assert result.finished
    assert result.answer_source == "llm"
    assert result.answer == "The camera observed red."


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("move_forward", {"distance_cm": 20}),
        (
            "update_belief",
            {
                "subject": "robot",
                "predicate": "battery_percent",
                "object": 80,
                "source": "user",
                "confidence": 0.9,
                "perspective": "user",
                "reason": "Check read-only scope",
            },
        ),
        (
            "downgrade_belief",
            {
                "belief_id": "b_000001",
                "new_confidence": 0.3,
                "reason": "Check read-only scope",
            },
        ),
    ],
)
def test_scoped_abstention_rejects_registered_actions_and_writes_before_dispatch(
    name, arguments
):
    def must_not_run(**kwargs):
        pytest.fail(f"Out-of-scope registered tool dispatched: {kwargs}")

    class InspectSchemas(ScriptedLLM):
        def chat(self, messages, tools=None, tool_choice=None):
            assert {tool["function"]["name"] for tool in tools} == {"query_belief"}
            return super().chat(messages, tools, tool_choice)

    registry = {
        "query_belief": _empty_read,
        name: must_not_run,
        "read_lidar": must_not_run,
    }
    llm = InspectSchemas(
        [
            call("query_belief", {"subject": "robot"}),
            call(name, arguments),
            say(ABSTENTION_SIGNAL),
        ]
    )
    observed = []
    result = run_agent(
        "Battery level?",
        llm,
        registry,
        max_steps=3,
        evidence_capability=BATTERY,
        on_step=lambda *entry: observed.append(entry),
    )
    assert result.error["code"] == "STEP_LIMIT"
    assert not result.answer
    assert [entry["tool"] for entry in result.tool_calls] == ["query_belief", name]
    assert (
        result.tool_calls[1]["guard"]["refused"]
        == "Tool request is outside the read-only evidence scope"
    )
    assert result.tool_calls[1]["result"]["error"]["code"] == "INVALID_ARGUMENT"
    assert [entry[1] for entry in observed] == ["query_belief", name]
    assert not any(entry[-1] for entry in observed)
