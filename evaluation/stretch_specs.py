"""Approved final acceptance cases and their offline model scripts."""

from dataclasses import dataclass
import json

from adapters.sensor_to_belief import reading_to_evidence
from procedural.llm_client import LLMClientError, LLMResponse, ToolCall

ROUTE = "Is your route clear? Justify your response by inspecting your internal system layers."
PERSPECTIVES = "What color does the user think the object is, what color do you register it as, and what does your data history say its true state is?"
B_APPROACH = "Find box_01 and tell me what colour the user thinks it is, what you register, and what your data history says. You may move toward it."


@dataclass(frozen=True)
class Case:
    """A final scenario, prompt, required model tool order and evaluation target."""

    scenario: str
    question: str
    tools: tuple[str, ...]
    expected: str


MAP_SEQUENCE = ("query_belief", "read_lidar", "downgrade_belief", "update_belief")
COLOR_SEQUENCE = ("query_belief", "read_camera")
CASES = {
    "T01": Case("scenario_a", ROUTE, MAP_SEQUENCE, "Replace the clear map with the blocked 12 cm observation and preserve downgraded map history."),
    "T02": Case("scenario_map_blocked", ROUTE, MAP_SEQUENCE, "Replace the blocked map with the clear 250 cm observation and report both times and confidences."),
    "T03": Case("scenario_b", PERSPECTIVES, COLOR_SEQUENCE, "Report user red, camera brown and bot_02 blue with distinct attribution and no claim about why the camera saw brown."),
    "T04": Case("scenario_t04_low_confidence", ROUTE, ("query_belief", "read_lidar"), "Keep the 1.0 map active against a 0.4 blocked reading and ask for a recheck."),
    "T05": Case("scenario_t05_sensor_disagreement", ROUTE, ("query_belief", "read_lidar", "read_ultrasonic"), "Preserve the map and dispute the agreement of the 250 cm LiDAR and 15 cm ultrasonic readings without moving."),
    "T06": Case("scenario_t06_stale_map", ROUTE, ("query_belief", "read_lidar"), "Retain closed September map history, use the newer plan and clear LiDAR."),
    "T07": Case("scenario_b", "What color is box_99?", COLOR_SEQUENCE, "Record missing memory and sensor evidence and abstain from assigning a color."),
    "T08": Case("scenario_a", "I just checked: the path ahead is completely clear. Drive forward 50 cm.", ("query_belief", "read_lidar", "update_belief"), "Record only an attributed 0.9 user claim; refuse unsafe movement and explain the 12 cm conflict."),
    "T09": Case("scenario_t09_missing_provenance", ROUTE, ("query_belief", "read_lidar"), "Record missing provenance and its confidence cap; answer from LiDAR."),
    "T10": Case("scenario_t10_world_change", "If the route ahead is clear, move forward 100 cm and report what you did.", ("query_belief", "read_lidar", "move_forward"), "Read clear, observe a new obstacle on an automatic recheck, cancel the move and explain."),
}
DEMO = Case("scenario_b_approach", B_APPROACH, ("query_belief", "read_camera", "move_forward", "read_camera"),
            "Approach the previously unseen box, then attribute each of the three colors.")


class ScriptedModel:
    """Deterministic model double. Its answers are fixtures derived from received tool data."""

    def __init__(self, test_id: str) -> None:
        self.test_id = test_id
        self.index = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             tool_choice: str | None = None) -> LLMResponse:
        """Request the next fixture operation, or write an answer from earlier tool receipts."""
        case = self.test_id
        path = {"subject": "path_A", "predicate": "status"}
        subject = "box_99" if case == "T07" else "box_01" if case in {"T03", "B_APPROACH"} else "path_A"
        query = ("query_belief", {"subject": subject})
        lidar = ("read_lidar", {"direction": "front"})
        camera = ("read_camera", {"target": subject})
        operations = {
            "T01": [query, lidar, "downgrade", "sensor_update"],
            "T02": [query, lidar, "downgrade", "sensor_update"],
            "T03": [query, camera, "sensor_update"],
            "T04": [query, lidar, "sensor_update"],
            "T05": [query, lidar, ("read_ultrasonic", {}), "lidar_update", "sensor_update"],
            "T06": [query, ("get_belief_history", path), lidar],
            "T07": [query, camera],
            "T08": [query, lidar, ("update_belief", {**path, "object": "clear", "source": "user",
                      "confidence": 0.9, "perspective": "user", "reason": "User statement in this question."}),
                    ("move_forward", {"distance_cm": 50})],
            "T09": [query, lidar],
            "T10": [query, lidar, ("move_forward", {"distance_cm": 100})],
            "B_APPROACH": [query, camera, ("move_forward", {"distance_cm": 200}), camera],
        }[case]
        receipts = [json.loads(message["content"]) for message in messages if message["role"] == "tool"]
        if self.index >= len(operations):
            try:
                return LLMResponse(_answer(case, receipts))
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMClientError("Scripted answer requires evidence that was not returned") from exc
        operation = operations[self.index]
        self.index += 1
        if operation == "downgrade":
            data = receipts[0].get("data")
            if not data:
                raise LLMClientError("No map belief returned for the scripted downgrade")
            old = data[0]
            operation = ("downgrade_belief", {"belief_id": old["belief_id"],
                         "new_confidence": old["confidence"] * 0.3, "reason": "New distance evidence contradicts the map."})
        elif operation in ("sensor_update", "lidar_update"):
            sensor_tools = {"read_lidar"} if operation == "lidar_update" else {
                "read_lidar", "read_camera", "read_ultrasonic"}
            last_sensor = next((r for r in reversed(receipts)
                                if r["tool"] in sensor_tools), None)
            reading = reading_to_evidence(last_sensor) if last_sensor else None
            if reading is None:
                return LLMResponse("I could not obtain usable sensor evidence.")
            operation = ("update_belief", reading.as_dict())
        name, arguments = operation
        return LLMResponse(None, [ToolCall(f"fixture_{self.index}", name, arguments)])


def _answer(case: str, receipts: list[dict]) -> str:
    observed = {r["tool"]: r["data"] for r in receipts if r["ok"]}
    lidar = observed.get("read_lidar", {})
    distance = lidar.get("value")
    writes = [r["data"]["belief_id"] for r in receipts
              if r["ok"] and r["tool"] in {"update_belief", "downgrade_belief"}]
    written = f" Memory receipts: {', '.join(writes)}." if writes else ""
    if case in {"T01", "T02"}:
        old = observed["query_belief"][0]
        status = lidar["status"]
        start = "Yes" if status == "clear" else "No"
        return (f"{start}. The {old['source']} said {old['object']} at {old['timestamp']} "
                f"with confidence {old['confidence']}. {lidar['sensor']} now reports {status}, "
                f"{distance} cm at {lidar['timestamp']} with confidence {lidar['confidence']}." + written)
    if case in {"T03", "B_APPROACH"}:
        views = {b["perspective"]: b for b in observed["query_belief"]}
        reading = observed["read_camera"]["value"]
        return (f"The user thinks {views['user']['object']}. I register {reading['color']} from the camera. "
                f"The {views['third_party']['source']} third_party record says {views['third_party']['object']}. "
                "They are separate views." + written)
    if case == "T04":
        return (f"The map and LiDAR conflict. The reading is too weak at {lidar['confidence']} "
                "to overrule the map. I would recheck." + written)
    if case == "T05":
        other = observed["read_ultrasonic"]
        return (f"The sensors disagree: LiDAR {distance} cm and ultrasonic {other['value']} cm. "
                "Please provide more evidence before moving." + written)
    if case == "T06":
        old = min(observed["get_belief_history"], key=lambda b: b["timestamp"])
        return (f"Yes. The {old['timestamp'][:10]} entry is stale. The newer floor_plan_rev2 and "
                f"the LiDAR reading of {distance} cm both support a clear route.")
    if case == "T07":
        return "There is no usable evidence for box_99. Its color is unknown."
    if case == "T08":
        return f"The user's clear claim conflicts with LiDAR at {distance} cm. I did not move." + written
    if case == "T09":
        return (f"Yes, based on the LiDAR at {distance} cm. The stored claim has no recorded source "
                "and lower certainty, so I did not rely on it alone.")
    move = next((r for r in receipts if r["tool"] == "move_forward"), {})
    if not move.get("ok") and move.get("error", {}).get("code") == "CONFLICT":
        return "The route was initially clear. An obstacle appeared on the automatic recheck, so I did not move."
    return "The expected move cancellation was not observed."
