"""Constants and illustrative distribution parameters for synthetic data
generation.

Every number here is a hand-picked, illustrative parameter for producing
plausible-*looking* synthetic operational data. NONE of it is derived from
or claimed to represent real-world SOC/CSE statistics -- see
docs/GENERATOR.md and the README for that disclaimer, stated once, clearly,
rather than repeated in every docstring.
"""

from __future__ import annotations

SECTORS: tuple[str, ...] = ("power", "banking", "telecom")
SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
CRITICALITY_TIERS: tuple[str, ...] = ("low", "medium", "high", "critical")

# Simulated observation window.
WINDOW_START = "2026-01-01T00:00:00"
WINDOW_DAYS = 180

# --- Asset generation -------------------------------------------------

# Every entity gets exactly one 'critical' and one 'high' asset (guaranteed,
# not random) so every entity can participate in the quiet_critical_asset
# use case, plus a random number of additional lower-tier assets for
# variety.
EXTRA_ASSET_COUNT_RANGE = (0, 2)          # additional medium/low assets
EXTRA_ASSET_TIER_WEIGHTS = {"medium": 0.6, "low": 0.4}

ASSET_TYPE_NAMES = (
    "SCADA Gateway", "Core Switch", "Domain Controller", "Payment Gateway",
    "Customer Database", "VPN Concentrator", "Email Server", "Billing System",
    "Network Firewall", "Log Aggregator", "Authentication Server", "Web Portal",
)

# --- Event volume per asset, over the whole window ---------------------
# (mean, stddev, floor) for a clipped Gaussian draw, by asset criticality_tier.
EVENT_VOLUME_BY_TIER = {
    "critical": (45.0, 12.0, 5),
    "high": (28.0, 8.0, 3),
    "medium": (14.0, 5.0, 1),
    "low": (6.0, 3.0, 0),
}

# Deliberately reduced volume for quiet_critical_asset anomalies/controls --
# materially less than the ~45-event critical-tier peer mean, but not zero.
QUIET_CRITICAL_EVENT_VOLUME = (9.0, 3.0, 2)

# Event severity distribution, conditional on the asset's criticality tier
# (low, medium, high, critical) -- weights sum to 1.0 per row.
EVENT_SEVERITY_WEIGHTS_BY_ASSET_TIER = {
    "critical": {"low": 0.30, "medium": 0.35, "high": 0.25, "critical": 0.10},
    "high": {"low": 0.35, "medium": 0.35, "high": 0.20, "critical": 0.10},
    "medium": {"low": 0.45, "medium": 0.35, "high": 0.15, "critical": 0.05},
    "low": {"low": 0.55, "medium": 0.30, "high": 0.12, "critical": 0.03},
}

EVENT_CATEGORIES = (
    "intrusion_attempt", "malware_signature", "policy_violation",
    "authentication_anomaly", "data_exfil_indicator", "port_scan",
    "denial_of_service_indicator", "configuration_drift",
)

# --- Case elevation: probability an event becomes a case, by severity ---
CASE_ELEVATION_PROBABILITY = {"critical": 0.95, "high": 0.75, "medium": 0.35, "low": 0.08}

# Case-open delay after the triggering event (minutes), uniform range.
CASE_OPEN_DELAY_MINUTES_RANGE = (1, 45)

# Closure duration (minutes): (mean, stddev, floor) by severity, for a
# clipped Gaussian draw. Deliberately correlated with severity so a naive
# "fast = suspicious" rule without peer/severity normalization would
# misfire -- this is intentional, see docs/GENERATOR.md.
CLOSURE_MINUTES_BY_SEVERITY = {
    "critical": (2880.0, 700.0, 120),
    "high": (1440.0, 500.0, 60),
    "medium": (600.0, 250.0, 30),
    "low": (180.0, 90.0, 10),
}

CASE_CLOSED_PROBABILITY = 0.90  # remainder stay 'open'

DISPOSITION_WEIGHTS_BY_SEVERITY = {
    "critical": {"confirmed_incident": 0.55, "remediated": 0.25, "no_action_required": 0.15, "false_positive_dismissed": 0.05},
    "high": {"confirmed_incident": 0.40, "remediated": 0.25, "no_action_required": 0.20, "false_positive_dismissed": 0.15},
    "medium": {"confirmed_incident": 0.20, "remediated": 0.20, "no_action_required": 0.30, "false_positive_dismissed": 0.30},
    "low": {"confirmed_incident": 0.05, "remediated": 0.10, "no_action_required": 0.35, "false_positive_dismissed": 0.50},
}

# Investigation note length (characters), roughly proportional to closure
# duration: note_length ~= closure_minutes * factor + noise, clipped.
NOTE_LENGTH_FACTOR = 0.12
NOTE_LENGTH_NOISE = (0, 40)   # uniform additive noise range
NOTE_LENGTH_RANGE = (20, 600)
MISSING_NOTE_LENGTH_PROBABILITY = 0.06   # ~6% of cases have no note length recorded

# --- Escalation ----------------------------------------------------------
ESCALATION_PROBABILITY_BY_SEVERITY = {"critical": 0.93, "high": 0.85, "medium": 0.25, "low": 0.08}
ESCALATION_TYPES = ("tier2_handoff", "management_notified", "external_coordination")
ESCALATION_DELAY_MINUTES_RANGE = (1, 30)

# --- Missing data ----------------------------------------------------------
MISSING_EVENT_ASSET_PROBABILITY = 0.05   # alert not tied to an inventoried asset

# --- Seeded anomaly / false-positive-control counts -----------------------
FAST_CLOSURE_ANOMALY_COUNT = 2
FAST_CLOSURE_FP_COUNT = 1
NO_ESCALATION_ANOMALY_COUNT = 2
NO_ESCALATION_FP_COUNT = 1
QUIET_CRITICAL_ANOMALY_COUNT = 2
QUIET_CRITICAL_FP_COUNT = 1

# Fixed values used when forcing an anomaly/control onto a chosen case.
FAST_CLOSURE_ANOMALY_MINUTES_RANGE = (2, 8)
FAST_CLOSURE_ANOMALY_NOTE_LENGTH_RANGE = (5, 20)
FAST_CLOSURE_FP_MINUTES_RANGE = (15, 25)
FAST_CLOSURE_FP_NOTE_LENGTH_RANGE = (400, 500)

MIN_ENTITIES = 12  # hard floor below which peer groups become too small to be meaningful
RECOMMENDED_ENTITY_RANGE = (15, 20)
