"""Shared, project-wide constants.

Kept deliberately tiny for Day 1. Anything generator- or detector-specific
belongs in those modules once they are built (Day 1 hours 4-8 and Day 2).
"""

from pathlib import Path

# Project root = two levels up from this file (src/config.py -> src/ -> root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "sat_sa.db"
GENERATED_DATA_DIR = PROJECT_ROOT / "data" / "generated"

# Fixed seed for all synthetic data generation (rule: deterministic, reproducible).
# The generator (not yet built) must use this seed and no other, so that the
# same dataset — including which entities/cases are seeded anomalies or
# false-positive controls — can be regenerated identically for grading/demo.
RANDOM_SEED = 42

# Canonical use-case type identifiers, shared between ground truth and
# (future) detector modules so both sides refer to the same vocabulary.
USE_CASE_FAST_CLOSURE = "fast_closure"
USE_CASE_NO_ESCALATION = "no_escalation"
USE_CASE_QUIET_CRITICAL_ASSET = "quiet_critical_asset"

USE_CASE_TYPES = (
    USE_CASE_FAST_CLOSURE,
    USE_CASE_NO_ESCALATION,
    USE_CASE_QUIET_CRITICAL_ASSET,
)

# Ground-truth status vocabulary (see docs/ARCHITECTURE.md, "Ground truth design").
GT_STATUS_NORMAL = "normal"
GT_STATUS_TRUE_ANOMALY = "true_anomaly"
GT_STATUS_FALSE_POSITIVE_CONTROL = "false_positive_control"

GT_STATUSES = (
    GT_STATUS_NORMAL,
    GT_STATUS_TRUE_ANOMALY,
    GT_STATUS_FALSE_POSITIVE_CONTROL,
)
