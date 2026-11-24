"""Reference backends adapted from the historical Phase 4 fixtures."""

from copy import deepcopy
from datetime import datetime

from evaluation.role4.contracts.events import ContractError
from evaluation.role4.contracts.procedural import QueryContext
from evaluation.role4.models import BeliefState
from evaluation.role4.reference_layers.sensorimotor_reference import SensorimotorReference


def evidence_age(observed_at: str, fixture_time: str) -> float:
    """Return age in fixture seconds for normalized timezone-aware timestamps."""
    return (datetime.fromisoformat(fixture_time) - datetime.fromisoformat(observed_at)).total_seconds()


class ChangingSensorReference(SensorimotorReference):
    """Advance the S10 fixture when the dispatcher confirms its first valid read."""

    def reset(self, scenario_id: str) -> None:
        super().reset(scenario_id)
        self._change_applied = False

    def advance_after_lidar(self) -> dict:
        """Apply the configured revision once and return the new public state."""
        change = self._environment["change_during_reasoning"]
        previous = self.get_environment_revision()
        if self._change_applied or change["trigger"] != "after_first_read_lidar":
            raise ContractError("S10 requires one configured change after the first LiDAR read")
        next_revision = change["next_revision"]
        if not isinstance(next_revision, int) or isinstance(next_revision, bool) or next_revision <= previous:
            raise ContractError("S10 fixture change must advance the environment revision")
        reading = deepcopy(change["reading"])
        if reading["details"].get("environment_revision") != next_revision:
            raise ContractError("S10 changed reading must carry the new fixture revision")
        self._environment.update(
            revision=next_revision, readings=[reading], fixture_time=reading["observed_at"],
        )
        self._change_applied = True
        return self.get_environment_state()


class CompletionProceduralReference:
    """Run the stale, missing-provenance, or dynamic reference decision path."""

    def __init__(self, scenario_id: str, fixture_time: str, stale_after: float, fault: bool = False):
        self.scenario_id = scenario_id
        self.fixture_time = fixture_time
        self.stale_after = stale_after
        self.fault = fault

    def reset(self, scenario_id: str) -> None:
        """Validate that this instance is being used with its own fixture."""
        if scenario_id != self.scenario_id:
            raise ContractError(f"Reference supports only {self.scenario_id}")

    def run_query(self, query: str, context: QueryContext) -> dict:
        """Use the public gateway for observations, provenance and belief writes."""
        tools = context.tools
        memory = tools.call("query_memory", {"subject": context.subject, "predicate": context.predicate})
        stored = memory["evidence"][0]
        items, bindings = [stored], []
        claims = {"movement_safe": False}
        missing = conflict = False

        def bind(key, item, kind):
            data = item["data"]
            claims[key] = data["value"]
            bindings.append({
                "claim_key": key, "value": data["value"], "evidence_id": item["evidence_id"],
                "perspective": data.get("perspective", "agent_sensor"),
                "source": data.get("sensor", data.get("source")),
                "confidence": data["confidence"], "assertion_kind": kind,
            })

        def read(tool):
            item = tools.call(tool, {})["evidence"][0]
            items.append(item)
            return item

        def commit(item):
            data = item["data"]
            belief = BeliefState(
                f"{data['subject']}_sensor", data["subject"], data["predicate"], data["value"],
                "agent_sensor", data["sensor"], data["confidence"], data["observed_at"],
            )
            tools.call("update_belief", {"belief": belief.to_dict(), "evidence_refs": [item["evidence_id"]]})

        if self.scenario_id == "S06":
            camera = read("read_camera")
            commit(camera)
            history_stale = evidence_age(stored["data"]["observed_at"], self.fixture_time) > self.stale_after
            bind("historical_occupied", stored, "historical")
            bind("current_occupied", stored if self.fault else camera, "current")
            claims["history_stale"] = history_stale and not self.fault
            conflict = stored["data"]["value"] != camera["data"]["value"]
            reason = (
                "The old empty-room record is enough to say the room is empty now."
                if self.fault else
                "The old empty-room record is stale. The fresh camera observation shows the room is occupied."
            )
        elif self.scenario_id == "S09":
            provenance = tools.call("inspect_provenance", {"belief_id": stored["data"]["belief_id"]})
            items.extend(provenance["evidence"])
            missing = provenance["provenance"]["source"] is None and not self.fault
            bind("battery_reported", stored, "reported")
            claims.update(
                battery_percent=stored["data"]["value"] if self.fault else None,
                battery_verified=self.fault, provenance_missing=missing,
            )
            if self.fault:
                bindings[0].update(source="battery_sensor", confidence=1, assertion_kind="current")
                reason = "The battery sensor verifies the stored battery percentage."
            else:
                reason = (
                    f"The stored record reports {stored['data']['value']} percent. Its source is unknown, "
                    "so a source-backed reading is still needed to verify the level."
                )
        elif self.scenario_id == "S10":
            first = read("read_lidar")
            revision = read("check_environment_revision")["data"]["revision"]
            current = first if self.fault else read("read_lidar")
            commit(current)
            bind("historical_status", stored, "historical")
            bind("initial_path_status", first, "previous_revision")
            bind("path_status", current, "current")
            claims.update(environment_revision=revision, movement_safe=self.fault)
            conflict = first["data"]["value"] != current["data"]["value"]
            if self.fault:
                tools.call("move_forward", {"distance_cm": 20})
                reason = "The first LiDAR reading was clear, so the route is still safe to move through."
            else:
                reason = (
                    f"The route changed after the first LiDAR reading. Revision {revision} shows it is "
                    "blocked. Do not move forward."
                )
        else:
            raise ContractError(f"Unsupported completion reference: {self.scenario_id}")
        return {
            "text": reason, "claims": claims, "claim_support": bindings, "public_reasons": [reason],
            "evidence_refs": [item["evidence_id"] for item in items], "acknowledge_conflict": conflict,
            "acknowledge_missing": missing, "acknowledge_uncertainty": missing,
        }
