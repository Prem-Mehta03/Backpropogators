"""Final scripted runs on canonical layers for grounding and action safety."""

import json

import pytest

from evaluation.role4.integration.offline import offline_guard
from evaluation.runner import run_case
from evaluation.stretch_checks import evaluate_case
from evaluation.stretch_specs import CASES, ScriptedModel


@pytest.mark.parametrize("test_id", ["T01", "T02", "T04", "T05", "T06", "T09", "T10"])
def test_canonical_grounding(test_id, tmp_path):
    with offline_guard() as blocked:
        log = run_case(test_id, tmp_path, run_id="offline")
    assert not blocked
    assert log["result"] == "PASS", [c for c in log["checks"] if not c["passed"]]
    calls = [entry for entry in log["tool_calls"] if not entry["auto"]]
    history = next(
        (
            i for i, entry in enumerate(calls)
            if entry["tool"] == "get_belief_history"
            and entry["args"].get("subject") == "path_A"
            and entry["args"].get("predicate") in (None, "status")
            and entry["result"]["ok"]
        ),
        None,
    )
    assert history is not None, "No successful history lookup for path_A/status"
    write_actions = {"downgrade_belief", "update_belief", "move_forward", "move_backward"}
    assert not any(entry["tool"] in write_actions for entry in calls[:history])


@pytest.mark.parametrize("history_issue", ["wrong_route", "current_only"])
def test_t06_needs_a_receipt_for_the_closed_route_entry(tmp_path, history_issue):
    with offline_guard():
        log = run_case("T06", tmp_path, run_id="offline")
    trace = json.loads(
        (tmp_path / "T06__offline" / log["trace_file"]).read_text(encoding="utf-8")
    )

    for receipts in (trace["tool_calls"], trace["observed_tools"]):
        receipt = next(r for r in receipts if r["tool"] == "get_belief_history")
        beliefs = receipt["result"]["data"]
        if history_issue == "wrong_route":
            receipt["args"]["subject"] = "path_B"
            for belief in beliefs:
                belief["subject"] = "path_B"
        else:
            receipt["result"]["data"] = [b for b in beliefs if b["status"] == "active"]

    checks = evaluate_case(
        "T06", CASES["T06"], trace["state_before"], trace["state_after"], trace,
        trace["observed_tools"], trace["memory_events"], trace["frames"],
    )
    assert {c["name"] for c in checks if not c["passed"]} == {"stale_map_receipt"}

    model = ScriptedModel("T06")
    messages = []
    for receipt in trace["tool_calls"]:
        assert model.chat(messages).tool_calls[0].name == receipt["tool"]
        messages.append({"role": "tool", "content": json.dumps(receipt["result"])})
    assert model.chat(messages).content.startswith("I cannot confirm")
