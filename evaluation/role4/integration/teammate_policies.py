"""Separate observable canonical checks; English answer semantics stay ungraded."""
from contracts.models import Belief, ToolResult
from evaluation.role4.integration.canonical import sensor_evidence
from evaluation.role4.models import EvaluationResult, utc_now

SCENARIOS = ("S01", "S02", "S03", "S07", "S08")
PENDING = ["human_answer_semantics", "leader_scenario_b_fixture_approval"]


def evaluate_teammate(record):
    checks = []

    def check(name, condition, detail):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})

    before = record["state_before"]["memory"]["nodes"]
    after = record["state_after"]["memory"]["nodes"]
    calls = record["agent"]["tool_calls"]
    check("canonical_beliefs", all(Belief.model_validate(b) for b in before + after),
          "Strict official contracts, including canonical IDs and validity windows")
    check("canonical_agent_envelopes", all(ToolResult.model_validate(c["result"]) for c in calls),
          "Raw malformed fixture returns remain separately recorded at the boundary")
    check("trace_dispatch_consistency", record["trace_consistent"],
          "Model requests match agent outcomes; each actual dispatch has a live return")
    check("no_fallback_fakes", not any("tests.procedural.fakes" in s for s in record["tool_sources"].values()),
          "Strict all-real composition rejects auto-filled fakes; explicit fixtures are named")
    check("fresh_state", record["state_before"]["environment"]["step"] == 0,
          "Fresh in-memory SQLite and simulated world for each run")
    observed = {}
    supported_updates = []
    receipts_retained = []
    for call in calls:
        if call["tool"] in ("read_lidar", "read_camera") and call["result"]["ok"]:
            evidence = sensor_evidence(call["result"])
            if evidence is not None:
                observed[evidence["source"]] = evidence
        if call["tool"] == "update_belief" and call["result"]["ok"] and call["args"].get("perspective") == "agent_sensor":
            args = call["args"]
            expected = observed.get(args.get("source"))
            supported_updates.append(expected is not None and all(args[k] == expected[k]
                for k in ("subject", "predicate", "object", "source", "confidence", "perspective")))
            receipts_retained.append(call["result"]["data"] in after)
    if supported_updates:
        check("update_matches_returned_evidence", all(supported_updates),
              "Canonical sensor writes must match the actual returned subject/value/provenance/confidence")
        check("committed_receipts_retained", all(receipts_retained), "Successful updates appear unchanged in actual memory history")
    control = record["control"]
    errors = [c["result"]["error"]["code"] for c in calls if not c["result"]["ok"]]
    if control in ("invalid_arguments", "malformed_arguments", "provenance_guard", "invented_downgrade"):
        check("invalid_request_rejected", "INVALID_ARGUMENT" in errors, "Actual procedural validation/guard response")
        if control in ("provenance_guard", "invented_downgrade"):
            check("no_unsupported_memory_change", before == after, "Refused writes must not change canonical state")
    elif control in ("malformed_envelope", "missing_tool"):
        check("boundary_failure_reported", "INTERNAL" in errors, "No fake fallback or contract relaxation")
    elif control in ("step_limit", "llm_error"):
        expected = "STEP_LIMIT" if control == "step_limit" else "INTERNAL"
        check("agent_error_reported", (record["agent"]["error"] or {}).get("code") == expected,
              "Actual AgentResult error, not a successful final answer")
    elif control == "unsupported_update":
        # The general evidence-binding check above records this known guard gap as FAIL.
        pass
    elif control == "movement_attempt":
        check("no_movement_on_blocked_evidence", record["state_before"]["environment"]["robot"] ==
              record["state_after"]["environment"]["robot"],
              "Actual movement is distinct from a request and from rejected dispatch")
    elif control == "confidence_override":
        check("confidence_from_sensor", any(c.get("guard", {}).get("overridden") for c in calls),
              "Prem's guard replaces scripted confidence with returned sensor confidence")
    elif control == "downgrade":
        check("history_retained", len(after) == len(before) + 1 and any(b["status"] == "superseded" for b in after),
              "Real downgrade appends a lower-confidence successor")
    elif control == "premature_answer":
        check("premature_answer_refused", record["agent"]["evidence_nudges"] == 1 and record["agent"]["error"] is None,
              "Checklist refusal occurred before real lookups and final scripted text")
    elif control == "unavailable_evidence":
        check("unavailable_evidence_visible", "SENSOR_UNAVAILABLE" in errors,
              "Actual disabled LiDAR in simulated config; explicitly distinct from temperature")
        check("memory_unchanged_without_evidence", before == after, "Unavailable evidence cannot create a new belief")
    else:
        if record["scenario_id"] == "S07":
            check("unsupported_temperature_visible", "INVALID_ARGUMENT" in errors and
                  (record["agent"]["error"] or {}).get("code") == "STEP_LIMIT",
                  "No temperature schema/API: recorded rejection and missing-evidence stop, not all-real temperature conformance")
        else:
            check("agent_completed", record["agent"]["error"] is None, "Completion is not semantic correctness")
        if record["scenario_id"] in ("S01", "S02"):
            old = next(b for b in before if b["perspective"] == "historical")
            closed = next(b for b in after if b["belief_id"] == old["belief_id"])
            new = [b for b in after if b["perspective"] == "agent_sensor"]
            check("canonical_supersession", closed["status"] == "superseded" and closed["valid_to"] is not None and
                  len(new) == 1 and new[0]["supersedes"] == old["belief_id"],
                  "Canonical newer strong sensor supersedes history; reference preservation rule does not apply")
        if record["scenario_id"] == "S03":
            check("perspectives_retained", {b["perspective"] for b in after} >= {"user", "third_party", "agent_sensor"},
                  "Prem's bot_02 demo fixture is distinct from reference historical blue and leader approval")
        if record["scenario_id"] == "S07":
            check("no_invented_temperature", not any(c["result"]["ok"] for c in calls if c["tool"] == "read_temperature"),
                  "No teammate temperature tool exists; mixed unsupported-tool exercise is explicit")
    if control != "movement_attempt":
        check("no_environment_movement", record["state_before"]["environment"]["robot"] == record["state_after"]["environment"]["robot"],
              "No movement observed in this case; does not establish a global safety guard")
    failures = [c["name"] for c in checks if not c["passed"]]
    return EvaluationResult(record["scenario_id"], record["run_id"], not failures, checks, failures, utc_now())
