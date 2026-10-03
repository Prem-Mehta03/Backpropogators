"""Observable trace checks. Response metadata is a contract, not an NLP grader."""

from collections import Counter
from evaluation.role4.models import ScenarioSpecification, TestRunRecord, EvaluationResult, utc_now


def evaluate(scenario: ScenarioSpecification, run: TestRunRecord, behavioral_policy=None) -> EvaluationResult:
    checks = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("scenario_identity", run.scenario_id == scenario.scenario_id and
          all(e.scenario_id == scenario.scenario_id for e in run.events),
          "Run and all events must belong to the requested scenario")
    initial = {b.belief_id: b.to_dict() for b in run.initial_beliefs}
    final = {b.belief_id: b.to_dict() for b in run.final_beliefs}
    check("unique_beliefs", len(initial) == len(run.initial_beliefs) and len(final) == len(run.final_beliefs),
          "Initial and final states must not contain duplicate belief IDs")
    check("initial_state", initial == {b.belief_id: b.to_dict() for b in scenario.initial_beliefs} and
          run.initial_environment_state == scenario.initial_environment_state and run.user_query == scenario.user_query,
          "Initial beliefs, environment and query must match the specification")

    # The complete trace must also record the inputs; final state alone is insufficient.
    input_events = [e for e in run.events if e.event_type not in {"boundary_call", "boundary_result"}]
    execution = input_events[0].payload.get("execution") if input_events else None
    snapshots = [("scenario_start", {"run_id": run.run_id, "name": scenario.name, "execution": execution}),
                 ("beliefs_before", {"beliefs": [b.to_dict() for b in run.initial_beliefs]}),
                 ("environment_before", {"state": run.initial_environment_state}),
                 ("user_query", {"text": run.user_query})]
    check("input_events", execution in {"stub", "integrated"} and len(input_events) >= 4 and
          all(input_events[i].event_type == kind and input_events[i].payload == payload
              for i, (kind, payload) in enumerate(snapshots)),
          "Trace must begin with scenario start, belief snapshot, environment snapshot and query")

    calls = [e.payload for e in run.events if e.event_type == "tool_call"]
    counts = Counter(call["tool_name"] for call in calls)
    for tool, minimum in Counter(scenario.expected_tools).items():
        check(f"required_tool:{tool}", counts[tool] >= minimum,
              f"Required tool {tool}: expected at least {minimum}, observed {counts[tool]}")
    for tool in scenario.forbidden_tools:
        check(f"forbidden_tool:{tool}", counts[tool] == 0, f"Forbidden tool {tool} was called {counts[tool]} times")
    cursor = 0
    for call in calls:
        if cursor < len(scenario.expected_tools) and call["tool_name"] == scenario.expected_tools[cursor]:
            cursor += 1
    check("tool_order", cursor == len(scenario.expected_tools),
          "Required tools must occur in the specified order, including repeated observations")

    evidence = {}
    pending = {}
    completed = {}
    seen_calls = set()
    replay = dict(initial)
    updates = []
    responses = []
    trace_errors = []
    allowed = {u["belief_id"]: u for u in scenario.expected_belief_updates}

    for event in run.events:
        payload = event.payload
        if responses and event.event_type not in {"boundary_call", "boundary_result"}:
            trace_errors.append("Execution events occurred after the final response")
        if event.event_type == "tool_call":
            call_id = payload["call_id"]
            if call_id in seen_calls:
                trace_errors.append(f"Duplicate call ID {call_id}")
            seen_calls.add(call_id)
            pending[call_id] = payload
        elif event.event_type == "tool_result":
            call_id = payload.get("call_id")
            call = pending.pop(call_id, None)
            if call is None or payload.get("tool_name") != call["tool_name"]:
                trace_errors.append(f"Unmatched tool result {call_id}")
                continue
            completed[call_id] = (call, payload)
            if payload.get("state") == "rejected" and (
                payload.get("authorized") is not False or payload.get("executed") is not False
            ):
                trace_errors.append(f"Rejected tool {call_id} cannot be authorized or physically executed")
            items = payload.get("evidence", [])
            if not isinstance(items, list):
                trace_errors.append(f"Invalid evidence list for {call_id}")
                continue
            for item in items:
                if not isinstance(item, dict) or not all(item.get(k) for k in ("evidence_id", "category", "data")):
                    trace_errors.append(f"Incomplete evidence in result {call_id}")
                    continue
                ref = item["evidence_id"]
                if not isinstance(ref, str) or not isinstance(item["category"], str):
                    trace_errors.append(f"Invalid evidence ID/category in result {call_id}")
                    continue
                if ref in evidence:
                    trace_errors.append(f"Duplicate evidence ID {ref}")
                evidence[ref] = item
        elif event.event_type == "belief_update":
            after = payload["after"]
            belief_id = after["belief_id"]
            updates.append(payload)
            if payload["before"] != replay.get(belief_id):
                trace_errors.append(f"Update before-state mismatch for {belief_id}")
            if belief_id not in allowed or any(after.get(k) != v for k, v in allowed.get(belief_id, {}).get("expected", {}).items()):
                trace_errors.append(f"Unexpected belief update for {belief_id}")
            references = payload["evidence_refs"]
            if any(ref not in evidence for ref in references):
                trace_errors.append(f"Unknown or future update evidence for {belief_id}")
            categories = {evidence[ref]["category"] for ref in references if ref in evidence}
            required = set(allowed.get(belief_id, {}).get("evidence_categories", []))
            if not required <= categories:
                trace_errors.append(f"Update {belief_id} missing evidence categories: {sorted(required - categories)}")
            grounded = False
            for ref in references:
                data = evidence.get(ref, {}).get("data", {})
                if isinstance(data, dict) and all(data.get(k) == after.get(k) for k in
                                                  ("subject", "predicate", "value", "confidence", "observed_at")):
                    grounded |= data.get("sensor", data.get("source")) == after.get("source")
            if not grounded:
                trace_errors.append(f"Update {belief_id} does not match its cited evidence value, source, confidence and timestamp")
            call_id = payload.get("call_id")
            pair = completed.get(call_id)
            if (not pair or pair[0]["tool_name"] != "update_belief" or
                    pair[0]["arguments"].get("belief") != after or pair[1].get("belief") != after):
                trace_errors.append(f"Belief update {belief_id} has no matching completed update_belief tool")
            replay[belief_id] = after
        elif event.event_type == "agent_response":
            responses.append(payload)
            if pending:
                trace_errors.append("Response was produced before pending tools completed")
            refs = payload["evidence_refs"]
            if any(ref not in evidence for ref in refs):
                trace_errors.append("Response cites unknown or future evidence")
        elif event.event_type not in {kind for kind, _ in snapshots} | {"boundary_call", "boundary_result"}:
            trace_errors.append(f"Unknown execution event type {event.event_type}")
    if pending:
        trace_errors.append(f"Tools without results: {sorted(pending)}")
    check("trace_integrity", not trace_errors, "; ".join(trace_errors) or "Tool results, references and update before-states are consistent")
    check("state_replay", replay == final, "Replaying recorded updates must reproduce the complete final belief state")
    for specification in scenario.expected_belief_updates:
        belief_id = specification["belief_id"]
        matching = [u for u in updates if u["after"]["belief_id"] == belief_id and
                    all(u["after"].get(k) == v for k, v in specification["expected"].items())]
        check(f"required_update:{belief_id}", len(matching) == 1,
              f"Belief {belief_id} requires exactly one recorded upsert with the specified value, source, confidence and perspective")
        check(f"final_belief:{belief_id}", belief_id in final and
              all(final[belief_id].get(k) == v for k, v in specification["expected"].items()),
              f"Final belief {belief_id} must match the required state")
    for belief_id in scenario.preserved_belief_ids:
        check(f"preserved_perspective:{belief_id}", final.get(belief_id) == initial[belief_id],
              f"Preserve belief {belief_id} including its value, perspective, provenance and timestamp")
    # All initial records not explicitly targeted remain unchanged, even if not named as preserved.
    untouched = set(initial) - set(allowed)
    check("no_unexpected_changes", all(final.get(key) == initial[key] for key in untouched) and
          set(final) <= set(initial) | set(allowed), "Only specified belief IDs may change or be added")

    check("one_final_response", len(responses) == 1, f"Expected one final response, observed {len(responses)}")
    response = responses[-1] if responses else {}
    requirements = scenario.expected_response_requirements
    categories = {evidence[ref]["category"] for ref in response.get("evidence_refs", []) if ref in evidence}
    required = set(requirements["evidence_categories"])
    check("response_evidence", required <= categories,
          f"Required response evidence categories missing: {', '.join(sorted(required - categories)) or 'none'}")
    for key in ("acknowledge_missing", "acknowledge_uncertainty", "acknowledge_conflict"):
        if requirements[key]:
            check(key, response.get(key) is True, f"Response must explicitly record {key}")
    for key, value in requirements["claims"].items():
        check(f"response_claim:{key}", response.get("claims", {}).get(key) == value,
              f"Response structured claim {key} must be {value!r}")
    if behavioral_policy is not None:
        if getattr(behavioral_policy, 'kind', None) in {'abstention', 's01_grounding'}:
            from evaluation.role4.midproject import midproject_checks
            checks.extend(midproject_checks(scenario, run, behavioral_policy))
        else:
            from evaluation.role4.behavioral import behavioral_checks
            checks.extend(behavioral_checks(scenario, run, behavioral_policy))
    failures = [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"]]
    return EvaluationResult(scenario.scenario_id, run.run_id, not failures, checks, failures, utc_now())
