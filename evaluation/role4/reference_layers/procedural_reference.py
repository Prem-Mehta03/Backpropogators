"""Rule-based S01 demonstration, using actual public tool dispatch calls."""

from evaluation.role4.contracts.events import ContractError
from evaluation.role4.models import BeliefState


class ProceduralReference:
    def __init__(self, *, skip_lidar=False):
        self.skip_lidar = skip_lidar
        self.scenario_id = None

    def reset(self, scenario_id):
        if scenario_id != "S01":
            raise ContractError("Procedural reference supports only S01")
        self.scenario_id = scenario_id

    def run_query(self, query, context):
        if self.scenario_id is None:
            raise ContractError("Procedural reference must be reset before execution")
        memory = context.tools.call("query_memory", {"subject": context.subject, "predicate": context.predicate})
        if not memory["beliefs"]:
            raise ContractError("S01 reference requires a stored map belief")
        refs = [item["evidence_id"] for item in memory["evidence"]]
        if self.skip_lidar:
            return {"text": "The stored map says clear. Move forward.", "evidence_refs": refs,
                    "claims": {"path_status": "clear", "movement_safe": True},
                    "acknowledge_conflict": False, "acknowledge_uncertainty": False, "acknowledge_missing": False}
        sensor = context.tools.call("read_lidar", {})
        reading = sensor["observation"]
        sensor_refs = [item["evidence_id"] for item in sensor["evidence"]]
        conflict = any(b["value"] != reading["value"] for b in memory["beliefs"])
        # Derive behavior from observed results, without reading evaluator expectations.
        belief = BeliefState(f"{reading['subject']}_sensor", reading["subject"], reading["predicate"], reading["value"],
                             "agent_sensor", reading["sensor"], reading["confidence"], reading["observed_at"])
        context.tools.call("update_belief", {"belief": belief.to_dict(), "evidence_refs": sensor_refs})
        blocked = reading["value"] == "blocked"
        distance = reading["details"].get("distance_cm")
        return {"text": f"The map reports {memory['beliefs'][0]['value']}; LiDAR observes {reading['value']} at {distance} cm. The sources disagree; do not move forward.",
                "evidence_refs": refs + sensor_refs, "claims": {"path_status": reading["value"], "movement_safe": not blocked},
                "claim_support": [{"claim_key": "path_status", "value": reading['value'],
                                   "evidence_id": sensor_refs[0], "source": reading['sensor'],
                                   "perspective": "agent_sensor", "confidence": reading['confidence']}],
                "public_reasons": ["The current physical-state claim uses returned LiDAR evidence; the map remains historical."],
                "acknowledge_conflict": conflict, "acknowledge_uncertainty": False, "acknowledge_missing": False}
