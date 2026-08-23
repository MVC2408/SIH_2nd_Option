"""Core synthetic data generation.

All randomness flows through a single `random.Random(seed)` instance passed
into every function here -- nothing module-level touches the global `random`
module, so two independent calls with the same seed produce byte-identical
output (see tests/test_generator.py::test_same_seed_is_deterministic).

Pipeline (see pipeline.py for the orchestrating call order):

    entities -> assets -> roles -> events -> cases -> escalations
        -> anomaly injection (mutates specific cases/escalations/asset volumes)
        -> ground truth assembly

Rule (Day 1 project rules, carried over unchanged): no record anywhere gets
an `is_anomaly`-style flag. Anomalies are created by giving specific,
already-otherwise-normal records genuinely unusual observable values;
ground truth is assembled as a completely separate table, in
`build_ground_truth`, and is the only place "this one is seeded" is ever
recorded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.generation import model


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

def build_entities(rng: random.Random, num_entities: int) -> list[dict]:
    """Deterministically assign IDs/sectors by index (round-robin across
    SECTORS), so peer-group *structure* never depends on the RNG draw order
    -- only entity *content* (name flavor text) does."""
    entities = []
    for i in range(num_entities):
        sector = model.SECTORS[i % len(model.SECTORS)]
        entity_id = f"ENT-{sector[:3].upper()}-{i // len(model.SECTORS) + 1:02d}"
        entity_name = f"{sector.capitalize()} Entity {i // len(model.SECTORS) + 1:02d} ({rng.choice(['Alpha','Bravo','Charlie','Delta','Echo','Foxtrot','Golf','Hotel'])})"
        entities.append(
            {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "entity_type": "CSE",
                "sector": sector,
                "notes": None,
            }
        )
    return entities


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

def build_assets(rng: random.Random, entities: list[dict]) -> list[dict]:
    """Every entity gets exactly one 'critical' and one 'high' asset
    (guaranteed, structural), plus 0-2 additional medium/low assets
    (random count/tier) for variety."""
    assets = []
    for entity in entities:
        entity_id = entity["entity_id"]
        asset_seq = 1

        for tier in ("critical", "high"):
            asset_name = rng.choice(model.ASSET_TYPE_NAMES)
            assets.append(
                {
                    "asset_id": f"AST-{entity_id}-{asset_seq:02d}",
                    "entity_id": entity_id,
                    "asset_name": asset_name,
                    "criticality_tier": tier,
                }
            )
            asset_seq += 1

        extra_count = rng.randint(*model.EXTRA_ASSET_COUNT_RANGE)
        for _ in range(extra_count):
            tier = _weighted_choice(rng, model.EXTRA_ASSET_TIER_WEIGHTS)
            asset_name = rng.choice(model.ASSET_TYPE_NAMES)
            assets.append(
                {
                    "asset_id": f"AST-{entity_id}-{asset_seq:02d}",
                    "entity_id": entity_id,
                    "asset_name": asset_name,
                    "criticality_tier": tier,
                }
            )
            asset_seq += 1

    return assets


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    cumulative = []
    total = 0.0
    for k in keys:
        total += weights[k]
        cumulative.append(total)
    r = rng.random() * total
    for k, c in zip(keys, cumulative):
        if r <= c:
            return k
    return keys[-1]


# ---------------------------------------------------------------------------
# Role assignment (which entities/assets host seeded anomalies/controls)
# ---------------------------------------------------------------------------

@dataclass
class RoleAssignment:
    fast_closure_anomaly_entities: list[str] = field(default_factory=list)
    fast_closure_fp_entities: list[str] = field(default_factory=list)
    no_escalation_anomaly_entities: list[str] = field(default_factory=list)
    no_escalation_fp_entities: list[str] = field(default_factory=list)
    # asset-level roles store asset_id directly, since the anomaly is a
    # property of one specific critical asset, not the whole entity.
    quiet_critical_anomaly_assets: list[str] = field(default_factory=list)
    quiet_critical_fp_assets: list[str] = field(default_factory=list)


def assign_roles(rng: random.Random, entities: list[dict], assets: list[dict]) -> RoleAssignment:
    entity_ids = [e["entity_id"] for e in entities]
    critical_asset_ids = [a["asset_id"] for a in assets if a["criticality_tier"] == "critical"]

    fc_pool = rng.sample(entity_ids, model.FAST_CLOSURE_ANOMALY_COUNT + model.FAST_CLOSURE_FP_COUNT)
    fc_anomaly = fc_pool[: model.FAST_CLOSURE_ANOMALY_COUNT]
    fc_fp = fc_pool[model.FAST_CLOSURE_ANOMALY_COUNT :]

    ne_pool = rng.sample(entity_ids, model.NO_ESCALATION_ANOMALY_COUNT + model.NO_ESCALATION_FP_COUNT)
    ne_anomaly = ne_pool[: model.NO_ESCALATION_ANOMALY_COUNT]
    ne_fp = ne_pool[model.NO_ESCALATION_ANOMALY_COUNT :]

    qc_pool = rng.sample(critical_asset_ids, model.QUIET_CRITICAL_ANOMALY_COUNT + model.QUIET_CRITICAL_FP_COUNT)
    qc_anomaly = qc_pool[: model.QUIET_CRITICAL_ANOMALY_COUNT]
    qc_fp = qc_pool[model.QUIET_CRITICAL_ANOMALY_COUNT :]

    return RoleAssignment(
        fast_closure_anomaly_entities=fc_anomaly,
        fast_closure_fp_entities=fc_fp,
        no_escalation_anomaly_entities=ne_anomaly,
        no_escalation_fp_entities=ne_fp,
        quiet_critical_anomaly_assets=qc_anomaly,
        quiet_critical_fp_assets=qc_fp,
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _random_timestamp(rng: random.Random) -> str:
    start = datetime.fromisoformat(model.WINDOW_START)
    day_offset = rng.uniform(0, model.WINDOW_DAYS)
    # Business-hours-weighted, not uniform: cluster around midday via a
    # triangular distribution instead of a flat 0-23 draw.
    hour = rng.triangular(0, 23, 13)
    minute = rng.uniform(0, 59)
    ts = start + timedelta(days=day_offset, hours=hour, minutes=minute)
    return ts.replace(microsecond=0).isoformat()


def build_events(rng: random.Random, entities: list[dict], assets: list[dict], roles: RoleAssignment) -> list[dict]:
    events = []
    event_seq = 1
    assets_by_entity: dict[str, list[dict]] = {}
    for a in assets:
        assets_by_entity.setdefault(a["entity_id"], []).append(a)

    for entity in entities:
        entity_id = entity["entity_id"]
        for asset in assets_by_entity.get(entity_id, []):
            asset_id = asset["asset_id"]
            tier = asset["criticality_tier"]

            if asset_id in roles.quiet_critical_anomaly_assets or asset_id in roles.quiet_critical_fp_assets:
                mean, sigma, floor = model.QUIET_CRITICAL_EVENT_VOLUME
            else:
                mean, sigma, floor = model.EVENT_VOLUME_BY_TIER[tier]
            volume = max(floor, round(rng.gauss(mean, sigma)))

            severity_weights = model.EVENT_SEVERITY_WEIGHTS_BY_ASSET_TIER[tier]

            for _ in range(volume):
                severity = _weighted_choice(rng, severity_weights)
                has_asset_link = rng.random() >= model.MISSING_EVENT_ASSET_PROBABILITY
                events.append(
                    {
                        "event_id": f"EVT-{event_seq:06d}",
                        "entity_id": entity_id,
                        "asset_id": asset_id if has_asset_link else None,
                        "occurred_at": _random_timestamp(rng),
                        "severity": severity,
                        "category": rng.choice(model.EVENT_CATEGORIES),
                        "case_id": None,  # filled in once cases are built, if elevated
                    }
                )
                event_seq += 1

    return events


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def build_cases(rng: random.Random, events: list[dict]) -> list[dict]:
    """Elevate a probability-weighted subset of events into cases.
    Mutates `events` in place to set event['case_id'] where elevated."""
    cases = []
    case_seq = 1

    for event in events:
        severity = event["severity"]
        if rng.random() > model.CASE_ELEVATION_PROBABILITY[severity]:
            continue

        case_id = f"CASE-{case_seq:06d}"
        case_seq += 1
        event["case_id"] = case_id

        opened = datetime.fromisoformat(event["occurred_at"]) + timedelta(
            minutes=rng.uniform(*model.CASE_OPEN_DELAY_MINUTES_RANGE)
        )

        is_closed = rng.random() < model.CASE_CLOSED_PROBABILITY
        closed_at = None
        note_length = None
        disposition = None
        if is_closed:
            mean, sigma, floor = model.CLOSURE_MINUTES_BY_SEVERITY[severity]
            closure_minutes = max(floor, rng.gauss(mean, sigma))
            closed_at = (opened + timedelta(minutes=closure_minutes)).replace(microsecond=0).isoformat()
            disposition = _weighted_choice(rng, model.DISPOSITION_WEIGHTS_BY_SEVERITY[severity])
            if rng.random() >= model.MISSING_NOTE_LENGTH_PROBABILITY:
                noise = rng.uniform(*model.NOTE_LENGTH_NOISE)
                note_length = int(
                    max(
                        model.NOTE_LENGTH_RANGE[0],
                        min(model.NOTE_LENGTH_RANGE[1], closure_minutes * model.NOTE_LENGTH_FACTOR + noise),
                    )
                )

        cases.append(
            {
                "case_id": case_id,
                "entity_id": event["entity_id"],
                "related_event_id": event["event_id"],
                "severity": severity,
                "opened_at": opened.replace(microsecond=0).isoformat(),
                "closed_at": closed_at,
                "status": "closed" if is_closed else "open",
                "disposition": disposition,
                "investigation_note_length": note_length,
            }
        )

    return cases


# ---------------------------------------------------------------------------
# Escalations
# ---------------------------------------------------------------------------

def build_escalations(rng: random.Random, cases: list[dict]) -> list[dict]:
    escalations = []
    esc_seq = 1
    for case in cases:
        severity = case["severity"]
        escalated = rng.random() < model.ESCALATION_PROBABILITY_BY_SEVERITY[severity]
        escalation_type = None
        escalated_at = None
        if escalated:
            escalation_type = rng.choice(model.ESCALATION_TYPES)
            delay = rng.uniform(*model.ESCALATION_DELAY_MINUTES_RANGE)
            opened = datetime.fromisoformat(case["opened_at"])
            escalated_at = (opened + timedelta(minutes=delay)).replace(microsecond=0).isoformat()

        escalations.append(
            {
                "escalation_id": f"ESC-{esc_seq:06d}",
                "case_id": case["case_id"],
                "escalated": 1 if escalated else 0,
                "escalation_type": escalation_type,
                "escalated_at": escalated_at,
            }
        )
        esc_seq += 1
    return escalations


# ---------------------------------------------------------------------------
# Anomaly / false-positive-control injection
#
# Deliberately mutates specific, already-generated records to produce
# genuinely unusual observable values. No record gains an is_anomaly flag;
# the only record of "this one was seeded" is the ground_truth table built
# afterwards in build_ground_truth().
# ---------------------------------------------------------------------------

def _pick_target_case(cases_by_entity: dict[str, list[dict]], entity_id: str, rng: random.Random) -> dict | None:
    """Pick a closed, high/critical-severity case belonging to `entity_id`,
    preferring an existing one (deterministic: sorted by case_id, first
    match) so injection doesn't depend on extra RNG draws beyond selecting
    which entities host which roles."""
    candidates = sorted(
        (
            c
            for c in cases_by_entity.get(entity_id, [])
            if c["status"] == "closed" and c["severity"] in ("high", "critical")
        ),
        key=lambda c: c["case_id"],
    )
    return candidates[0] if candidates else None


def inject_fast_closure_anomalies(
    rng: random.Random, cases: list[dict], roles: RoleAssignment
) -> list[tuple[dict, str]]:
    """Force specific cases' closure duration to be anomalously fast.
    Returns [(case, kind)] where kind is 'true_anomaly' or 'false_positive_control'."""
    cases_by_entity: dict[str, list[dict]] = {}
    for c in cases:
        cases_by_entity.setdefault(c["entity_id"], []).append(c)

    seeded: list[tuple[dict, str]] = []

    for entity_id in roles.fast_closure_anomaly_entities:
        case = _pick_target_case(cases_by_entity, entity_id, rng)
        if case is None:
            continue
        opened = datetime.fromisoformat(case["opened_at"])
        minutes = rng.uniform(*model.FAST_CLOSURE_ANOMALY_MINUTES_RANGE)
        case["closed_at"] = (opened + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
        case["investigation_note_length"] = rng.randint(*model.FAST_CLOSURE_ANOMALY_NOTE_LENGTH_RANGE)
        case["disposition"] = "confirmed_incident"  # looks like a normal disposition, nothing self-flagging
        seeded.append((case, "true_anomaly"))

    for entity_id in roles.fast_closure_fp_entities:
        case = _pick_target_case(cases_by_entity, entity_id, rng)
        if case is None:
            continue
        opened = datetime.fromisoformat(case["opened_at"])
        minutes = rng.uniform(*model.FAST_CLOSURE_FP_MINUTES_RANGE)
        case["closed_at"] = (opened + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
        case["investigation_note_length"] = rng.randint(*model.FAST_CLOSURE_FP_NOTE_LENGTH_RANGE)
        case["disposition"] = "false_positive_dismissed"
        seeded.append((case, "false_positive_control"))

    return seeded


def inject_no_escalation_anomalies(
    rng: random.Random, cases: list[dict], escalations: list[dict], roles: RoleAssignment
) -> list[tuple[dict, str]]:
    """Force specific high/critical cases to be non-escalated. Returns
    [(case, kind)] for ground-truth assembly."""
    cases_by_entity: dict[str, list[dict]] = {}
    for c in cases:
        cases_by_entity.setdefault(c["entity_id"], []).append(c)
    escalations_by_case = {e["case_id"]: e for e in escalations}

    seeded: list[tuple[dict, str]] = []
    used_case_ids: set[str] = set()

    def pick_unused(entity_id: str) -> dict | None:
        candidates = sorted(
            (
                c
                for c in cases_by_entity.get(entity_id, [])
                if c["status"] == "closed"
                and c["severity"] in ("high", "critical")
                and c["case_id"] not in used_case_ids
            ),
            key=lambda c: c["case_id"],
        )
        return candidates[0] if candidates else None

    for entity_id in roles.no_escalation_anomaly_entities:
        case = pick_unused(entity_id)
        if case is None:
            continue
        used_case_ids.add(case["case_id"])
        esc = escalations_by_case.get(case["case_id"])
        if esc is None:
            continue
        esc["escalated"] = 0
        esc["escalation_type"] = None
        esc["escalated_at"] = None
        # Disposition intentionally left as whatever normal generation
        # produced -- no special marker distinguishes this from a normal case.
        seeded.append((case, "true_anomaly"))

    for entity_id in roles.no_escalation_fp_entities:
        case = pick_unused(entity_id)
        if case is None:
            continue
        used_case_ids.add(case["case_id"])
        esc = escalations_by_case.get(case["case_id"])
        if esc is None:
            continue
        esc["escalated"] = 0
        esc["escalation_type"] = None
        esc["escalated_at"] = None
        # This IS distinguishable via disposition -- a documented policy
        # exception, unlike the true anomaly above.
        case["disposition"] = "no_escalation_per_approved_exception"
        seeded.append((case, "false_positive_control"))

    return seeded
