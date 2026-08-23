"""Data-quality validation for a freshly generated dataset.

Runs entirely in Python over the in-memory row lists, before anything is
written to disk. `validate_dataset` returns a list of problem strings;
`GenerationError` is raised by the pipeline if that list is non-empty --
generation fails loudly rather than silently shipping bad data.
"""

from __future__ import annotations

from datetime import datetime

from src.generation import model


class GenerationError(Exception):
    """Raised when generated data fails validation. Carries the full list
    of problems found, not just the first one, so all issues can be fixed
    in one pass instead of one-at-a-time."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} data-quality problem(s):\n" + "\n".join(f"  - {p}" for p in problems))


def _check_unique(rows: list[dict], key: str, table: str, problems: list[str]) -> None:
    ids = [r[key] for r in rows]
    seen = set()
    for i in ids:
        if i in seen:
            problems.append(f"{table}: duplicate {key} '{i}'")
        seen.add(i)


def _valid_iso(ts: str | None) -> bool:
    if ts is None:
        return True
    try:
        datetime.fromisoformat(ts)
        return True
    except ValueError:
        return False


def validate_dataset(
    entities: list[dict],
    assets: list[dict],
    events: list[dict],
    cases: list[dict],
    escalations: list[dict],
    ground_truth: list[dict],
) -> list[str]:
    problems: list[str] = []

    # --- uniqueness ----------------------------------------------------
    _check_unique(entities, "entity_id", "entity", problems)
    _check_unique(assets, "asset_id", "asset", problems)
    _check_unique(events, "event_id", "event", problems)
    _check_unique(cases, "case_id", "case_record", problems)
    _check_unique(escalations, "escalation_id", "escalation", problems)
    _check_unique(ground_truth, "ground_truth_id", "ground_truth", problems)

    entity_ids = {e["entity_id"] for e in entities}
    asset_ids = {a["asset_id"] for a in assets}
    event_ids = {e["event_id"] for e in events}
    case_ids = {c["case_id"] for c in cases}

    # --- foreign-key consistency ----------------------------------------
    for a in assets:
        if a["entity_id"] not in entity_ids:
            problems.append(f"asset {a['asset_id']}: unknown entity_id '{a['entity_id']}'")

    for e in events:
        if e["entity_id"] not in entity_ids:
            problems.append(f"event {e['event_id']}: unknown entity_id '{e['entity_id']}'")
        if e["asset_id"] is not None and e["asset_id"] not in asset_ids:
            problems.append(f"event {e['event_id']}: unknown asset_id '{e['asset_id']}'")
        if e["case_id"] is not None and e["case_id"] not in case_ids:
            problems.append(f"event {e['event_id']}: unknown case_id '{e['case_id']}'")

    for c in cases:
        if c["entity_id"] not in entity_ids:
            problems.append(f"case_record {c['case_id']}: unknown entity_id '{c['entity_id']}'")
        if c["related_event_id"] is not None and c["related_event_id"] not in event_ids:
            problems.append(f"case_record {c['case_id']}: unknown related_event_id '{c['related_event_id']}'")

    for esc in escalations:
        if esc["case_id"] not in case_ids:
            problems.append(f"escalation {esc['escalation_id']}: unknown case_id '{esc['case_id']}'")

    for gt in ground_truth:
        if gt["entity_id"] not in entity_ids:
            problems.append(f"ground_truth {gt['ground_truth_id']}: unknown entity_id '{gt['entity_id']}'")
        if gt["case_id"] is not None and gt["case_id"] not in case_ids:
            problems.append(f"ground_truth {gt['ground_truth_id']}: unknown case_id '{gt['case_id']}'")
        if gt["asset_id"] is not None and gt["asset_id"] not in asset_ids:
            problems.append(f"ground_truth {gt['ground_truth_id']}: unknown asset_id '{gt['asset_id']}'")

    # --- timestamps & closure > creation ----------------------------------
    for c in cases:
        if not _valid_iso(c["opened_at"]):
            problems.append(f"case_record {c['case_id']}: invalid opened_at '{c['opened_at']}'")
        if not _valid_iso(c["closed_at"]):
            problems.append(f"case_record {c['case_id']}: invalid closed_at '{c['closed_at']}'")
        if c["status"] == "closed":
            if c["closed_at"] is None:
                problems.append(f"case_record {c['case_id']}: status='closed' but closed_at is NULL")
            elif _valid_iso(c["opened_at"]) and _valid_iso(c["closed_at"]):
                if datetime.fromisoformat(c["closed_at"]) <= datetime.fromisoformat(c["opened_at"]):
                    problems.append(f"case_record {c['case_id']}: closed_at is not after opened_at")
        elif c["status"] == "open" and c["closed_at"] is not None:
            problems.append(f"case_record {c['case_id']}: status='open' but closed_at is set")

    for e in events:
        if not _valid_iso(e["occurred_at"]):
            problems.append(f"event {e['event_id']}: invalid occurred_at '{e['occurred_at']}'")

    for esc in escalations:
        if not _valid_iso(esc["escalated_at"]):
            problems.append(f"escalation {esc['escalation_id']}: invalid escalated_at '{esc['escalated_at']}'")
        if esc["escalated"] == 1 and esc["escalated_at"] is None:
            problems.append(f"escalation {esc['escalation_id']}: escalated=1 but escalated_at is NULL")

    # --- controlled vocabularies -------------------------------------------
    for a in assets:
        if a["criticality_tier"] not in model.CRITICALITY_TIERS:
            problems.append(f"asset {a['asset_id']}: invalid criticality_tier '{a['criticality_tier']}'")
    for c in cases:
        if c["severity"] not in model.SEVERITIES:
            problems.append(f"case_record {c['case_id']}: invalid severity '{c['severity']}'")
    for e in events:
        if e["severity"] not in model.SEVERITIES:
            problems.append(f"event {e['event_id']}: invalid severity '{e['severity']}'")
    for ent in entities:
        if ent["sector"] not in model.SECTORS:
            problems.append(f"entity {ent['entity_id']}: invalid sector '{ent['sector']}'")
    for gt in ground_truth:
        if gt["use_case_type"] not in ("fast_closure", "no_escalation", "quiet_critical_asset"):
            problems.append(f"ground_truth {gt['ground_truth_id']}: invalid use_case_type '{gt['use_case_type']}'")
        if gt["status"] not in ("normal", "true_anomaly", "false_positive_control"):
            problems.append(f"ground_truth {gt['ground_truth_id']}: invalid status '{gt['status']}'")
        if not gt["explanation"]:
            problems.append(f"ground_truth {gt['ground_truth_id']}: empty explanation")

    # --- required fields populated -----------------------------------------
    for ent in entities:
        if not ent["entity_name"]:
            problems.append(f"entity {ent['entity_id']}: missing entity_name")
    for a in assets:
        if not a["asset_name"]:
            problems.append(f"asset {a['asset_id']}: missing asset_name")

    # --- sufficient peer group sizes ----------------------------------------
    from collections import Counter

    sector_counts = Counter(e["sector"] for e in entities)
    for sector, count in sector_counts.items():
        if count < 4:
            problems.append(f"sector '{sector}' has only {count} entities; need >= 4 for a meaningful peer baseline")

    critical_asset_count = sum(1 for a in assets if a["criticality_tier"] == "critical")
    if critical_asset_count < 4:
        problems.append(f"only {critical_asset_count} critical-tier assets exist; need >= 4 for a meaningful peer baseline")

    # --- seeded anomalies / controls present, per use case -----------------
    for use_case in ("fast_closure", "no_escalation", "quiet_critical_asset"):
        statuses = [gt["status"] for gt in ground_truth if gt["use_case_type"] == use_case]
        if "true_anomaly" not in statuses:
            problems.append(f"no true_anomaly ground truth present for use_case '{use_case}'")
        if "false_positive_control" not in statuses:
            problems.append(f"no false_positive_control ground truth present for use_case '{use_case}'")

    return problems
