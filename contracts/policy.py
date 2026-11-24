"""Shared evidence thresholds agreed for contract v1.1."""

LIVE_SENSOR_MIN = 0.6
WEAK_SENSOR_MAX = 0.5
STRONG_BELIEF_MIN = 0.8
MISSING_SOURCE_CAP = 0.5
DOWNGRADE_FACTOR = 0.3
USER_STATEMENT_CONF = 0.9
STALE_AFTER_S = 7 * 24 * 3600
BLOCKED_AT_CM = 30
RECHECK_MARGIN_CM = 30
MAX_CLAIM_REFUSALS = 3
MAX_MODEL_CALLS = 12  # was 10; live T05 needed at least 11 calls to write its own answer
