"""Evidence checklist and provenance guard, tested with the scripted LLM (no network)."""

from __future__ import annotations

from typing import Any

from procedural.agent import run_agent
from procedural.checklist import describe_requirement, missing_evidence
from procedural.update_guard import check_memory_call
from scripts.tool_wiring import build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say

REGISTRY, _ = build_tool_registry(use_real=False)
Q = "Is your route clear?"


def entry(
    tool: str, ok: bool = True, code: str | None = None, data: Any = None
) -> dict[str, Any]:
    error = None if ok else {"code": code, "message": "x", "retryable": False}
    return {
        "tool": tool,
        "args": {},
        "result": {"ok": ok, "data": data, "error": error},
    }


# ---- checklist as a pure function -------------------------------------------------------------


def test_nothing_called_means_everything_is_missing() -> None:
    assert missing_evidence([], (("query_belief",), ("read_lidar", "read_camera"))) == [
        "query_belief",
        "one of read_lidar, read_camera",
    ]


def test_describe_requirement_single_and_group() -> None:
    assert describe_requirement(("a",)) == "a"
    assert describe_requirement(("a", "b")) == "one of a, b"


def test_not_found_and_sensor_unavailable_count_as_an_attempt() -> None:
    log = [
        entry("query_belief", False, "NOT_FOUND"),
        entry("read_lidar", False, "SENSOR_UNAVAILABLE"),
    ]
    assert missing_evidence(log, (("query_belief",), ("read_lidar",))) == []


def test_invalid_argument_and_internal_do_not_count() -> None:
    log = [
        entry("query_belief", False, "INVALID_ARGUMENT"),
        entry("read_lidar", False, "INTERNAL"),
    ]
    assert missing_evidence(log, (("query_belief",), ("read_lidar",))) == [
        "query_belief",
        "read_lidar",
    ]


# ---- checklist inside the loop ----------------------------------------------------------------


def test_premature_answer_is_refused_then_accepted_after_evidence() -> None:
    llm = ScriptedLLM(
        [
            say("It is clear."),
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            say("Blocked."),
        ]
    )
    out = run_agent(Q, llm, REGISTRY)
    assert out.finished and out.answer == "Blocked."
    assert out.evidence_nudges == 1
    note = llm.seen[1][-1]
    assert note["role"] == "user" and "query_belief" in note["content"]
    assert any(
        m.get("content") == "It is clear." for m in out.messages
    )  # kept in history


def test_answer_after_evidence_needs_no_nudge() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            say("ok"),
        ]
    )
    assert run_agent(Q, llm, REGISTRY).evidence_nudges == 0


def test_route_requires_each_registered_range_sensor_before_answering() -> None:
    from contracts.validators import error_result

    registry = {
        **REGISTRY,
        "read_ultrasonic": lambda: error_result(
            "read_ultrasonic", "SENSOR_UNAVAILABLE", "No echo"
        ),
    }
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "query"),
            call("get_belief_history", {"subject": "path_A"}, "queryh"),
            call("read_lidar", {}, "lidar"),
            say("The route is blocked."),
            call("read_ultrasonic", {}, "ultrasound"),
            say("The LiDAR reports blocked and no ultrasonic reading was available."),
        ]
    )
    out = run_agent(Q, llm, registry)
    assert out.finished and out.evidence_nudges == 1
    assert "read_ultrasonic" in llm.seen[4][-1]["content"]


def test_not_found_lookup_still_satisfies_memory_requirement() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "ghost"}, "c1"),
            call("read_lidar", {}, "c2"),
            say("Memory has nothing; lidar says blocked."),
        ]
    )
    out = run_agent(Q, llm, REGISTRY)
    assert out.finished and out.evidence_nudges == 0


def test_invalid_argument_lookup_does_not_satisfy_the_checklist() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {}, "c1"),  # missing subject -> INVALID_ARGUMENT
            call("read_lidar", {}, "c2"),
            say("done"),
            say("done"),
        ]
    )
    out = run_agent(Q, llm, REGISTRY, max_steps=4)
    assert out.error and out.error["code"] == "STEP_LIMIT"
    assert "query_belief" in out.error["message"]


def test_never_complying_model_hits_step_limit_naming_missing_items() -> None:
    llm = ScriptedLLM([say("guess")] * 5)
    out = run_agent(Q, llm, REGISTRY, max_steps=3)
    assert out.error and out.error["code"] == "STEP_LIMIT"
    assert (
        "query_belief" in out.error["message"] and "read_lidar" in out.error["message"]
    )
    assert out.evidence_nudges == 3 and out.answer == ""


def test_empty_required_evidence_disables_the_checklist() -> None:
    out = run_agent(Q, ScriptedLLM([say("hi")]), REGISTRY, required_evidence=())
    assert out.finished and out.evidence_nudges == 0


# ---- provenance guard as a pure function ------------------------------------------------------

BELIEF = {
    "belief_id": "b_000123",
    "confidence": 1.0,
    "subject": "path_A",
    "predicate": "status",
    "object": "clear",
    "perspective": "historical",
}
LIDAR = {
    "sensor": "lidar_front",
    "unit": "cm",
    "confidence": 0.98,
    "value": 12,
    "status": "blocked",
}
KNOWN = ("path_A",)
LOG = [entry("query_belief", data=[BELIEF]), entry("read_lidar", data=LIDAR)]
SENSOR_UPDATE = {
    "subject": "path_A",
    "predicate": "status",
    "object": "blocked",
    "source": "lidar_front",
    "confidence": 0.5,
    "perspective": "agent_sensor",
    "reason": "live reading",
}


def test_downgrade_unknown_id_is_refused() -> None:
    d = check_memory_call(
        "downgrade_belief", {"belief_id": "b_999999", "new_confidence": 0.1}, LOG
    )
    assert d.error and "b_999999" in d.error


def test_downgrade_must_lower_confidence() -> None:
    d = check_memory_call(
        "downgrade_belief", {"belief_id": "b_000123", "new_confidence": 1.0}, LOG
    )
    assert d.error and "lower" in d.error


def test_valid_downgrade_value_is_replaced_by_the_rule() -> None:
    args = {"belief_id": "b_000123", "new_confidence": 0.5, "reason": "r"}
    d = check_memory_call("downgrade_belief", args, LOG)
    assert d.error is None and d.args["new_confidence"] == 0.3  # 1.0 * DOWNGRADE_FACTOR
    assert d.overridden == {"new_confidence": {"model_value": 0.5, "used": 0.3}}


def test_downgrade_that_already_matches_the_rule_is_not_flagged() -> None:
    args = {"belief_id": "b_000123", "new_confidence": 0.3, "reason": "r"}
    d = check_memory_call("downgrade_belief", args, LOG)
    assert d.error is None and d.args == args and d.overridden == {}


def test_downgrade_value_scales_with_the_old_confidence() -> None:
    log = [
        entry(
            "query_belief",
            data=[{**BELIEF, "belief_id": "b_000009", "confidence": 0.8}],
        ),
        entry("read_lidar", data=LIDAR),
    ]
    d = check_memory_call(
        "downgrade_belief", {"belief_id": "b_000009", "new_confidence": 0.1}, log
    )
    assert d.args["new_confidence"] == 0.24


def test_downgrade_rule_value_stays_under_the_weak_sensor_line_and_above_the_floor() -> (
    None
):
    from procedural.update_guard import DOWNGRADE_FACTOR

    assert 1.0 * DOWNGRADE_FACTOR < 0.5  # Guidelines 5: under 0.5 counts as weak
    assert 0.4 * DOWNGRADE_FACTOR >= 0.1  # a still-credible belief stays visible


def test_user_and_third_party_views_are_never_downgraded() -> None:
    for perspective in ("user", "third_party"):
        belief = {
            "belief_id": "b_000002",
            "confidence": 0.9,
            "perspective": perspective,
        }
        log = [entry("query_belief", data=[belief])]
        d = check_memory_call(
            "downgrade_belief", {"belief_id": "b_000002", "new_confidence": 0.1}, log
        )
        assert d.error and perspective in d.error and "ask the person" in d.error


def test_a_historical_belief_can_still_be_downgraded() -> None:
    belief = {**BELIEF, "belief_id": "b_000001"}
    log = [entry("query_belief", data=[belief]), entry("read_lidar", data=LIDAR)]
    d = check_memory_call(
        "downgrade_belief", {"belief_id": "b_000001", "new_confidence": 0.1}, log
    )
    assert d.error is None and d.args["new_confidence"] == 0.3


def test_a_persons_own_statement_gets_the_fixed_user_confidence() -> None:
    user = {**SENSOR_UPDATE, "perspective": "user", "source": "user", "confidence": 0.3}
    d = check_memory_call("update_belief", user, [], KNOWN)
    assert d.error is None and d.args["confidence"] == 0.9
    assert d.overridden == {"confidence": {"model_value": 0.3, "used": 0.9}}


def test_sensor_update_with_unread_source_is_refused() -> None:
    d = check_memory_call(
        "update_belief", {**SENSOR_UPDATE, "source": "camera_front"}, LOG, KNOWN
    )
    assert d.error and "camera_front" in d.error


def test_failed_sensor_read_is_not_a_source() -> None:
    log = [entry("read_lidar", False, "SENSOR_UNAVAILABLE")]
    assert check_memory_call("update_belief", SENSOR_UPDATE, log, KNOWN).error


def test_sensor_update_confidence_is_replaced_by_the_reading() -> None:
    d = check_memory_call("update_belief", SENSOR_UPDATE, LOG, KNOWN)
    assert d.error is None and d.args["confidence"] == 0.98
    assert d.overridden == {"confidence": {"model_value": 0.5, "used": 0.98}}


def test_matching_confidence_is_not_flagged() -> None:
    d = check_memory_call(
        "update_belief", {**SENSOR_UPDATE, "confidence": 0.98}, LOG, KNOWN
    )
    assert d.error is None and d.overridden == {}


def test_reading_cannot_be_reused_to_write_a_contradictory_value_or_subject() -> None:
    for invented in (
        {**SENSOR_UPDATE, "object": "clear"},
        {**SENSOR_UPDATE, "subject": "path_B"},
    ):
        refusal = check_memory_call(
            "update_belief", invented, LOG, ("path_A", "path_B")
        )
        assert refusal.error and "does not match" in refusal.error


def test_other_perspectives_and_tools_pass_through() -> None:
    third = {
        **SENSOR_UPDATE,
        "perspective": "third_party",
        "source": "bot_02",
        "confidence": 0.7,
    }
    d = check_memory_call("update_belief", third, [], KNOWN)
    assert d.error is None and d.args == third
    assert check_memory_call("read_lidar", {}, []).args == {}


def test_malformed_args_pass_through_to_normal_validation() -> None:
    assert check_memory_call("downgrade_belief", {"belief_id": 5}, LOG).error is None
    assert (
        check_memory_call("update_belief", {"perspective": "agent_sensor"}, LOG).error
        is None
    )


# ---- full Scenario A, scripted ----------------------------------------------------------------


def test_scenario_a_full_run_resolves_the_conflict_with_guard_override() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call(
                "downgrade_belief",
                {
                    "belief_id": "b_000123",
                    "new_confidence": 0.2,
                    "reason": "lidar blocked",
                },
                "c3",
            ),
            call("update_belief", SENSOR_UPDATE, "c4"),
            say(
                "No, stored belief says clear, but lidar_front reads blocked. Downgraded "
                "b_000123 and recorded b_000124."
            ),
        ]
    )
    out = run_agent(Q, llm, REGISTRY)
    assert out.finished and out.evidence_nudges == 0
    assert [c["tool"] for c in out.tool_calls] == [
        "query_belief",
        "get_belief_history",
        "read_lidar",
        "downgrade_belief",
        "update_belief",
    ]
    assert all(c["result"]["ok"] for c in out.tool_calls)
    last = out.tool_calls[-1]
    assert last["args"]["confidence"] == 0.98  # what actually ran
    assert last["guard"]["overridden"]["confidence"]["model_value"] == 0.5
    assert "guard" not in out.tool_calls[0]


def test_guard_refusal_reaches_the_model_and_is_logged() -> None:
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call(
                "downgrade_belief",
                {"belief_id": "b_424242", "new_confidence": 0.1, "reason": "r"},
                "c3",
            ),
            say("Could not downgrade: the id was invalid."),
        ]
    )
    out = run_agent(Q, llm, REGISTRY)
    refused = out.tool_calls[3]
    assert refused["result"]["error"]["code"] == "INVALID_ARGUMENT"
    assert "refused" in refused["guard"]
    assert "b_424242" in llm.seen[4][-1]["content"]


# ---- subject guard: a write may only name an entity seen in this run ---------------------------


def test_write_to_a_mistyped_subject_is_refused() -> None:
    args = {**SENSOR_UPDATE, "subject": "path_a"}
    d = check_memory_call("update_belief", args, LOG, KNOWN, "Is your route clear?")
    assert d.error and "path_a" in d.error and "path_A" in d.error


def test_subject_returned_by_memory_is_allowed_without_a_glossary() -> None:
    seen = [entry("query_belief", data=[{**BELIEF, "subject": "path_A"}]), LOG[1]]
    assert check_memory_call("update_belief", SENSOR_UPDATE, seen).error is None


def test_subject_named_in_the_question_is_allowed() -> None:
    args = {
        **SENSOR_UPDATE,
        "subject": "box_77",
        "perspective": "user",
        "source": "user",
    }
    assert (
        check_memory_call("update_belief", args, [], (), "Is box_77 green?").error
        is None
    )


def test_camera_object_id_counts_as_seen() -> None:
    camera = entry(
        "read_camera", data={"value": {"object_id": "box_01", "color": "brown"}}
    )
    args = {
        **SENSOR_UPDATE,
        "subject": "box_01",
        "perspective": "user",
        "source": "user",
    }
    assert check_memory_call("update_belief", args, [camera], (), "x").error is None


def test_loop_refuses_a_mistyped_subject_write_and_the_model_can_retry() -> None:
    bad = {**SENSOR_UPDATE, "subject": "path_a"}
    llm = ScriptedLLM(
        [
            call("query_belief", {"subject": "path_A"}, "c1"),
            call("get_belief_history", {"subject": "path_A"}, "c1h"),
            call("read_lidar", {}, "c2"),
            call("update_belief", bad, "c3"),
            call("update_belief", SENSOR_UPDATE, "c4"),
            say("The route is blocked. I recorded b_000124."),
        ]
    )
    out = run_agent(Q, llm, REGISTRY, known_subjects={"path_A": "the path"})
    refused = out.tool_calls[3]
    assert (
        not refused["result"]["ok"]
        and "not an entity seen" in refused["guard"]["refused"]
    )
    assert out.tool_calls[4]["result"]["ok"]
