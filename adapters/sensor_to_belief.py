"""Sensor-to-belief adapter: the one place a reading becomes belief evidence.

SKELETON WITH PLACEHOLDERS. Everything that depends on Vyom or Prem is marked
``TODO(confirm)``. This module never touches the belief store: it only turns a
sensor reading into the arguments that ``update_belief`` expects
(Guidelines 4.5: subject, predicate, object, source, confidence, perspective,
reason). Prem's tool layer decides what to do with the result.

Draft choices from the contract (not invented): source = sensor name,
confidence = reading confidence, perspective = "agent_sensor".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# --- placeholders awaiting confirmation --------------------------------------
# TODO(confirm, Vyom/Yash): which subject a LiDAR reading describes. The
# Guidelines' example belief is path_A / status; Scenario A's map belief is
# assumed to use the same pair so the two can conflict.
LIDAR_SUBJECT = "path_A"
LIDAR_PREDICATE = "status"
CAMERA_PREDICATE = "color"
PERSPECTIVE = "agent_sensor"
# TODO(confirm, Prem/Vyom): the return shape below (a dict of update_belief
# arguments) and who calls this function.


PERSPECTIVES = ("user", "agent_sensor", "historical", "third_party")


@dataclass(frozen=True)
class BeliefEvidence:
    """Arguments for ``update_belief``; field names follow Guidelines 4.5.

    Validated on construction against the Belief field rules in Guidelines 4.2
    (no contract model exists yet for update_belief arguments, so this is the
    adapter's own check). Raises ValueError on a bad value.
    """

    subject: str
    predicate: str
    object: Any
    source: str
    confidence: float
    perspective: str
    reason: str

    def __post_init__(self) -> None:
        for name in ("subject", "predicate", "source", "reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string, got {value!r}")
        if isinstance(self.object, bool) is False and not isinstance(
            self.object, (str, int, float)
        ):
            raise ValueError(f"object must be string, number or boolean, got {self.object!r}")
        conf = self.confidence
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise ValueError(f"confidence must be a number in [0, 1], got {conf!r}")
        if self.perspective not in PERSPECTIVES:
            raise ValueError(f"perspective must be one of {PERSPECTIVES}, got {self.perspective!r}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get(reading: Any, name: str) -> Any:
    """Read a field from a SensorReading model or a plain dict."""
    return reading[name] if isinstance(reading, dict) else getattr(reading, name)


def reading_to_evidence(reading: Any) -> BeliefEvidence | None:
    """Convert one SensorReading into belief evidence.

    Accepts a SensorReading (model or dict) or the ToolResult envelope dict a
    sensor tool returned. A failed envelope (ok=false) gives None.

    Returns None when the reading carries no usable evidence: status "unknown"
    or "error", a camera reading with no object, or a position reading (poses
    are not beliefs in the current plan). The caller then treats evidence as
    missing, which is the behaviour Guidelines section 5 requires.
    """
    if isinstance(reading, dict) and "ok" in reading and "data" in reading:
        if not reading["ok"] or reading["data"] is None:
            return None
        reading = reading["data"]
    sensor, status = _get(reading, "sensor"), _get(reading, "status")
    value, ts = _get(reading, "value"), _get(reading, "timestamp")
    if status in ("unknown", "error"):
        return None

    if sensor.startswith("lidar"):
        return BeliefEvidence(
            subject=LIDAR_SUBJECT,
            predicate=LIDAR_PREDICATE,
            object=status,
            source=sensor,
            confidence=float(_get(reading, "confidence")),
            perspective=PERSPECTIVE,
            reason=f"{sensor} read {value} cm ({status}) at {ts}",
        )
    if sensor.startswith("camera") and isinstance(value, dict):
        if value.get("object_id") is None or value.get("color") is None:
            return None
        return BeliefEvidence(
            subject=str(value["object_id"]),
            predicate=CAMERA_PREDICATE,
            object=str(value["color"]),
            source=sensor,
            confidence=float(_get(reading, "confidence")),
            perspective=PERSPECTIVE,
            reason=f"{sensor} saw {value['object_id']} as {value['color']} at {ts}",
        )
    return None  # position or any sensor not yet mapped
