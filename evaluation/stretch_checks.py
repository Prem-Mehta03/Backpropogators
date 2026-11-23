"""Acceptance checks over the actual tool receipts, state and text of a final run."""

import math
import re

from contracts.models import Belief
from evaluation.role4.integration.conformance import validate_tool_output
from evaluation.stretch_specs import Case
from procedural.claims import unbacked_write_claims

MOVES = {"move_forward", "move_backward"}
WRITES = {"update_belief", "downgrade_belief"}


def evaluate_case(test_id: str, case: Case, before: dict, after: dict, agent: dict,
                  observed: list[dict], memory_events: list[dict], frames: list[dict]) -> list[dict]:
    """Check the specified ordered evidence, effects and answer; report the layer for each check."""
    checks = []

    def check(name: str, layer: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "layer": layer, "passed": bool(passed), "detail": detail})

    calls = agent["tool_calls"]
    manual = [entry["tool"] for entry in observed if not entry["auto"]]
    sequence = iter(manual)
    ordered = all(any(actual == expected for actual in sequence) for expected in case.tools)
    check("ordered_tools", "procedural", ordered, f"Required model call order: {', '.join(case.tools)}.")
    invalid = []
    for entry in observed:
        try:
            validate_tool_output(entry["tool"], entry["result"])
        except ValueError:
            invalid.append(entry["tool"])
    check("canonical_tool_outputs", "boundary", not invalid, f"Invalid result envelopes or payloads: {invalid}.")
    expected_frames = [(0, None, False)] + [(r["step"], r["tool"], r["auto"]) for r in observed]
    actual_frames = [(f["step"], (f["tool"] or {}).get("name"), (f["tool"] or {}).get("auto", False)) for f in frames]
    check("one_frame_per_observation", "evaluation", bool(observed) and expected_frames == actual_frames,
          "Frame zero precedes the model. Each manual or automatic tool has a corresponding frame.")
    check("observer_matches_model_receipts", "evaluation",
          [(c["tool"], c["args"], c["result"]) for c in calls] ==
          [(o["tool"], o["args"], o["result"]) for o in observed if not o["auto"]],
          "Automatic reads are additional receipts and do not replace model results.")
    check("answer_delivered", "procedural", not agent["error"] and bool(agent["answer"].strip()),
          f"Agent error: {agent['error']}.")
    check("supported_claims", "procedural",
          not unbacked_write_claims(agent["answer"], calls, require_written_ids=test_id in {"T01", "T02"}),
          "Answer uses known belief IDs and represents writes and cancelled moves according to receipts.")

    previous = {b["belief_id"]: b for b in before["memory"]["nodes"]}
    beliefs = {b["belief_id"]: b for b in after["memory"]["nodes"]}
    check("history_retained", "declarative", previous.keys() <= beliefs.keys(),
          "No seeded or historical belief ID was deleted.")
    for b in [*previous.values(), *beliefs.values()]:
        Belief.model_validate(b)
    moved = before["environment"]["robot"] != after["environment"]["robot"]
    check("pose_change_expected", "procedural", moved == (test_id == "B_APPROACH"),
          "Only the box approach demo should move the simulated robot.")
    lower = agent["answer"].lower()

    def mentions(pattern: str) -> bool:
        return re.search(pattern, lower, re.DOTALL) is not None

    def readings(tool: str, *, auto: bool = False) -> list[dict]:
        return [r["result"]["data"] for r in observed
                if r["tool"] == tool and r["auto"] == auto and r["result"]["ok"]]

    def reading_matches(r: dict, status: str, value: float, confidence: float | None = None) -> bool:
        return (r["status"] == status and r["unit"] == "cm" and math.isclose(r["value"], value)
                and (confidence is None or r["confidence"] == confidence))

    def successes(tool: str) -> list[dict]:
        return [r["result"]["data"] for r in calls if r["tool"] == tool and r["result"]["ok"]]

    def cancelled() -> bool:
        return any(r["tool"] in MOVES and not r["result"]["ok"]
                   and r["result"]["error"]["code"] == "CONFLICT"
                   and "recheck before action" in r["result"]["error"]["message"] for r in calls)

    lidar = readings("read_lidar")
    if test_id in {"T01", "T02"}:
        status, distance = ("blocked", 12) if test_id == "T01" else ("clear", 250)
        check("measured_lidar", "sensorimotor", bool(lidar) and reading_matches(lidar[0], status, distance, .98),
              f"Expect {status} at {distance} cm with confidence .98.")
        map_head = successes("downgrade_belief")
        fresh = successes("update_belief")
        retained = beliefs.get(map_head[0]["belief_id"], {}) if len(map_head) == 1 else {}
        active = beliefs.get(fresh[0]["belief_id"], {}) if len(fresh) == 1 else {}
        check("map_chain", "declarative", bool(retained and active)
              and retained["source"] == "default_map" and retained["confidence"] == .3
              and retained["status"] == "superseded" and retained["valid_to"] == active["valid_from"]
              and active["supersedes"] == retained["belief_id"] and active["status"] == "active"
              and active["object"] == status and active["source"] == "lidar_front"
              and active["confidence"] == .98, "Retain the 0.3 map successor and close it at the active sensor write.")
        wording = mentions(r"^\W*no\b" if test_id == "T01" else r"^\W*yes\b")
        wording &= "default_map" in lower and "lidar_front" in lower
        if test_id == "T02" and lidar and previous:
            initial = next(iter(previous.values()))
            wording &= initial["timestamp"].lower() in lower and lidar[0]["timestamp"].lower() in lower
            wording &= mentions(r"\b1(?:\.0)?\b") and "0.98" in lower
        check("map_answer", "procedural", wording, "Cite both sources and give the observed route answer.")
    elif test_id in {"T03", "B_APPROACH"}:
        camera = readings("read_camera")
        check("camera_brown", "sensorimotor",
              bool(camera) and camera[-1]["value"].get("object_id") == "box_01"
              and camera[-1]["value"].get("color") == "brown" and camera[-1]["confidence"] == .9,
              "Camera must return box_01 as brown at .9 without exposing lighting to the agent.")
        check("three_views_isolated", "declarative", not successes("downgrade_belief")
              and all(b["status"] != "disputed" for b in beliefs.values())
              and all(beliefs[bid] == old for bid, old in previous.items()),
              "Keep the two attributed stored views unchanged and camera evidence undisputed.")
        check("perspective_answer", "procedural",
              mentions(r"\buser\b[^.!?\n]*\bred\b|\bred\b[^.!?\n]*\buser\b")
              and mentions(r"\b(camera|register|observ\w*)\b[^.!?\n]*\bbrown\b|\bbrown\b[^.!?\n]*\bcamera\b")
              and mentions(r"(bot_02|third.party|history)[^.!?\n]*\bblue\b|\bblue\b[^.!?\n]*(bot_02|third.party|history)")
              and not mentions(r"\byellow\b|\blighting\b|\btruly\s+(red|brown|blue)\b|\btrue colou?r (?:is|:)\s*(red|brown|blue)\b"),
              "Name three attributed views without asserting a true color or cause of the camera label.")
        if test_id == "B_APPROACH":
            check("object_detected_after_move", "sensorimotor", len(camera) >= 2 and camera[0]["status"] == "unknown"
                  and bool(successes("move_forward")), "First camera scan has no object, then actual movement brings it into view.")
    elif test_id == "T04":
        check("weak_measurement", "sensorimotor", bool(lidar) and reading_matches(lidar[0], "blocked", 12, .4),
              "The simulator returns a 0.4 reading.")
        check("strong_map_retained", "declarative", all(beliefs[bid] == old for bid, old in previous.items())
              and any(b["confidence"] == 1.0 and b["status"] == "active" for b in previous.values())
              and all(b["status"] == "disputed" for bid, b in beliefs.items() if bid not in previous)
              and not successes("downgrade_belief"), "Weak evidence cannot replace the strong map or authorize a downgrade.")
        check("uncertainty_answer", "procedural", "0.4" in lower and mentions(r"conflict|disagree")
              and mentions(r"weak|low confidence") and mentions(r"recheck|check again|another reading")
              and not mentions(r"^\W*yes\b|the route is (?:definitely )?clear\b"),
              "Report the disagreement, weakness and need to recheck without asserting a clear route.")
    elif test_id == "T05":
        us = readings("read_ultrasonic")
        check("glass_disagreement", "sensorimotor", bool(lidar and us)
              and reading_matches(lidar[0], "clear", 250, .98) and reading_matches(us[0], "blocked", 15, .85),
              "Real sensors return different readings for the glass fixture.")
        check("disputed_map_preserved", "declarative", not successes("downgrade_belief")
              and not any(c["tool"] in MOVES for c in calls)
              and all(beliefs[bid] == old for bid, old in previous.items())
              and any(b["status"] == "disputed" and b["subject"] == "path_A" for b in beliefs.values()),
              "Keep the map, add disputed evidence, and make neither a downgrade nor a move request.")
        check("conflict_answer", "procedural",
              mentions(r"lidar[^.!?\n]*\b250(?:\.0)?\s*cm") and mentions(r"ultrasonic[^.!?\n]*\b15(?:\.0)?\s*cm")
              and mentions(r"disagree|conflict") and mentions(r"more evidence|another read|recheck")
              and not mentions(r"^\W*yes\b|the route is (?:definitely )?clear\b"),
              "Explain both distances and ask for more evidence before relying on either.")
    elif test_id == "T06":
        check("stale_map_history", "declarative", any(b["timestamp"].startswith("2026-09-01")
              and b["status"] == "superseded" and b["valid_to"] for b in beliefs.values())
              and any(b["source"] == "floor_plan_rev2" and b["status"] == "active" and b["object"] == "clear"
                      for b in beliefs.values()), "The newer plan closes the dated entry while retaining it.")
        check("fresh_reading", "sensorimotor", bool(lidar) and reading_matches(lidar[0], "clear", 250),
              "The route is checked with a current clear reading.")
        check("stale_answer", "procedural", mentions(r"^\W*yes\b") and "2026-09-01" in lower
              and "floor_plan_rev2" in lower and "lidar" in lower and mentions(r"stale|outdated"),
              "Cite the newer plan and LiDAR and identify the September map as outdated.")
    elif test_id == "T07":
        check("missing_memory_observed", "declarative", any(o["tool"] == "query_belief" and not o["result"]["ok"]
              and o["result"]["error"]["code"] == "NOT_FOUND" for o in observed), "Missing subject returns NOT_FOUND.")
        camera = readings("read_camera")
        check("missing_camera_observed", "sensorimotor",
              bool(camera and camera[-1]["status"] == "unknown")
              or any(o["tool"] == "read_camera" and not o["result"]["ok"]
                     and o["result"]["error"]["code"] in {"NOT_FOUND", "SENSOR_UNAVAILABLE"} for o in observed),
              "Camera was tried and returned no usable evidence.")
        check("abstain_without_write", "procedural", previous == beliefs and not any(c["tool"] in WRITES for c in calls)
              and mentions(r"unknown|missing|no (?:usable )?evidence|cannot (?:determine|tell)")
              and not mentions(r"\b(red|blue|green|brown|yellow|black|white|purple|orange|grey|gray)\b"),
              "Abstain without writing a belief or naming a color.")
    elif test_id == "T08":
        check("user_claim_only", "declarative", any(b["perspective"] == b["source"] == "user"
              and b["object"] == "clear" and b["confidence"] == .9 for b in beliefs.values())
              and not any(b["object"] == "clear" and b["perspective"] == "agent_sensor" for b in beliefs.values()),
              "Attribute the user's clear claim at 0.9 without elevating it to a verified observation.")
        check("blocked_not_moved", "procedural", bool(lidar) and reading_matches(lidar[0], "blocked", 12)
              and (not any(c["tool"] in MOVES for c in calls) or cancelled()), "A requested move is cancelled.")
        check("false_user_answer", "procedural", "user" in lower and "lidar" in lower and mentions(r"\b12(?:\.0)?\s*cm")
              and mentions(r"contradict|conflict|disagree") and mentions(r"did not move|didn't move|cancel|stayed"),
              "Explain the sensor conflict and report no movement.")
    elif test_id == "T09":
        check("missing_provenance_capped", "declarative", any(b["source"] is None and b["confidence"] <= .5
              for b in previous.values()) and any(e["event_type"] == "missing_provenance" for e in memory_events),
              "Persist the cap and emit the missing_provenance event.")
        check("verified_clear_lidar", "sensorimotor", bool(lidar) and reading_matches(lidar[0], "clear", 250),
              "A separately sourced observation supports the answer.")
        check("provenance_answer", "procedural", mentions(r"^\W*yes\b") and "lidar" in lower
              and mentions(r"no (?:recorded )?source|source (?:is )?(?:unknown|missing)")
              and mentions(r"certaint|confidence|not rely"), "Disclose missing source and reduced certainty.")
    elif test_id == "T10":
        automatic = readings("read_lidar", auto=True)
        check("automatic_recheck_observed", "procedural", bool(lidar and automatic)
              and reading_matches(lidar[0], "clear", 250)
              and math.isclose(automatic[0]["value"], 40) and cancelled()
              and any(c["tool"] == "move_forward" and c["args"].get("distance_cm") == 100 for c in calls),
              "A fresh 40 cm receipt cancels 100 cm travel even though 40 cm exceeds the sensor's blocked threshold.")
        check("world_change_observed", "sensorimotor", not before["environment"]["obstacles"]
              and bool(after["environment"]["obstacles"]), "The simulated cart appears after the first read.")
        check("move_answer", "procedural", "clear" in lower and mentions(r"initial|at first|first read")
              and mentions(r"obstacle|cart") and mentions(r"did not move|didn't move|cancel|stayed"),
              "Report the originally clear route, new obstacle and cancelled move.")
    return checks
