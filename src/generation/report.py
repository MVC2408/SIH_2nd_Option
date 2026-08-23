"""Print a human-readable summary of a generated dataset."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime


def _closure_minutes(case: dict) -> float | None:
    if case["status"] != "closed" or case["closed_at"] is None:
        return None
    return (datetime.fromisoformat(case["closed_at"]) - datetime.fromisoformat(case["opened_at"])).total_seconds() / 60.0


def print_summary(
    entities: list[dict],
    assets: list[dict],
    events: list[dict],
    cases: list[dict],
    escalations: list[dict],
    ground_truth: list[dict],
) -> None:
    print("=" * 78)
    print("SYNTHETIC DATASET SUMMARY")
    print("=" * 78)
    print(f"entities            : {len(entities)}")
    print(f"assets              : {len(assets)}")
    print(f"events              : {len(events)}")
    print(f"cases               : {len(cases)}")
    print(f"escalations         : {len(escalations)}")
    print(f"ground_truth rows   : {len(ground_truth)}")

    print("\n--- peer group (sector) distribution ---")
    for sector, count in sorted(Counter(e["sector"] for e in entities).items()):
        print(f"  {sector:<10} {count} entities")

    print("\n--- asset criticality distribution ---")
    for tier, count in sorted(Counter(a["criticality_tier"] for a in assets).items()):
        print(f"  {tier:<10} {count} assets")

    print("\n--- event severity distribution ---")
    for sev, count in sorted(Counter(e["severity"] for e in events).items()):
        print(f"  {sev:<10} {count} events")

    print("\n--- case severity distribution ---")
    for sev, count in sorted(Counter(c["severity"] for c in cases).items()):
        print(f"  {sev:<10} {count} cases")

    closure_minutes = [m for c in cases if (m := _closure_minutes(c)) is not None]
    if closure_minutes:
        print("\n--- closure-time summary (closed cases, minutes) ---")
        print(f"  n      = {len(closure_minutes)}")
        print(f"  min    = {min(closure_minutes):.1f}")
        print(f"  median = {statistics.median(closure_minutes):.1f}")
        print(f"  mean   = {statistics.mean(closure_minutes):.1f}")
        print(f"  max    = {max(closure_minutes):.1f}")

    events_per_asset = Counter(e["asset_id"] for e in events if e["asset_id"])
    per_asset_counts = list(events_per_asset.values())
    if per_asset_counts:
        print("\n--- activity summary (events per asset) ---")
        print(f"  min    = {min(per_asset_counts)}")
        print(f"  median = {statistics.median(per_asset_counts):.1f}")
        print(f"  max    = {max(per_asset_counts)}")

    print("\n--- ground truth: anomalies & controls by use case ---")
    for use_case in ("fast_closure", "no_escalation", "quiet_critical_asset"):
        statuses = Counter(gt["status"] for gt in ground_truth if gt["use_case_type"] == use_case)
        print(
            f"  {use_case:<22} normal={statuses.get('normal', 0):<5} "
            f"true_anomaly={statuses.get('true_anomaly', 0):<3} "
            f"false_positive_control={statuses.get('false_positive_control', 0)}"
        )
    print("=" * 78)
