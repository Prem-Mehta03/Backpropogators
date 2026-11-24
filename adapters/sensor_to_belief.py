"""Sensor-to-belief adapter: the one place a reading becomes belief evidence.

Defaults chosen by Asvin where the Guidelines were silent (see the Interface
Guide). This module never touches the belief store: it only turns a
sensor reading into the arguments that ``update_belief`` expects
(Guidelines 4.5: subject, predicate, object, source, confidence, perspective,
reason). Prem's tool layer decides what to do with the result.

Draft choices from the contract (not invented): source = sensor name,
confidence = reading confidence, perspective = "agent_sensor".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from contracts.sensor_evidence import reading_claim

# --- decided defaults (see the Sensorimotor Interface Guide, section 7) ----
# A LiDAR reading is evidence about path_A / status, so Scenario A's sensor
# evidence can conflict with the map belief. Change here if the team seeds a
# different subject.
LIDAR_SUBJECT = "path_A"
LIDAR_PREDICATE = "status"
CAMERA_PREDICATE = "color"
PERSPECTIVE = "agent_sensor"
# Return shape: BeliefEvidence, a dataclass holding the update_belief arguments.


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
    claim = reading_claim(reading)
    if claim is None:
        return None
    subject, predicate, observed = claim
    if predicate == CAMERA_PREDICATE:
        reason = f"{sensor} saw {subject} as {observed} at {ts}"
    else:
        reason = f"{sensor} read {value} cm ({status}) at {ts}"
    return BeliefEvidence(
        subject=subject,
        predicate=predicate,
        object=observed,
        source=sensor,
        confidence=float(_get(reading, "confidence")),
        perspective=PERSPECTIVE,
        reason=reason,
    )
