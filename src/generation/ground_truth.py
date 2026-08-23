"""Ground truth assembly.

This module is the ONLY place in the generator that records which
case/asset was deliberately seeded and why. It runs strictly AFTER all
operational data (entities, assets, events, cases, escalations, including
anomaly injection) already exists, and never adds anything to those
records -- it only produces a separate list of ground_truth rows.

Coverage is deliberately broad, not just the seeded rows: every closed case
gets a fast_closure ground-truth row, every closed high/critical case gets a
no_escalation row, and every critical-tier asset gets a quiet_critical_asset
row -- almost all labeled 'normal'. This lets Day 2 compute real
precision/recall/false-positive-rate over the whole dataset, not just the
handful of cases we deliberately tampered with (see project roadmap,
"Validation Strategy").
"""

from __future__ import annotations


def _event_count_by_asset(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        if e["asset_id"]:
            counts[e["asset_id"]] = counts.get(e["asset_id"], 0) + 1
    return counts


def build_ground_truth(
    entities: list[dict],
    assets: list[dict],
    cases: list[dict],
    events: list[dict],
    fast_closure_seeded: list[tuple[dict, str]],
    no_escalation_seeded: list[tuple[dict, str]],
    quiet_critical_anomaly_assets: list[str],
    quiet_critical_fp_assets: list[str],
) -> list[dict]:
    rows: list[dict] = []
    gt_seq = 1

    def next_id() -> str:
        nonlocal gt_seq
        gid = f"GT-{gt_seq:06d}"
        gt_seq += 1
        return gid

    # --- fast_closure: every closed case -----------------------------------
    fc_status_by_case = {case["case_id"]: status for case, status in fast_closure_seeded}
    for case in cases:
        if case["status"] != "closed":
            continue
        status = fc_status_by_case.get(case["case_id"], "normal")
        if status == "true_anomaly":
            explanation = (
                f"Seeded: case {case['case_id']} (entity {case['entity_id']}, severity "
                f"{case['severity']}) closed with an anomalously short duration and a "
                f"{case['investigation_note_length']}-character note -- forced fast "
                f"closure with no documented justification."
            )
        elif status == "false_positive_control":
            explanation = (
                f"Seeded: case {case['case_id']} (entity {case['entity_id']}, severity "
                f"{case['severity']}) closed quickly but with disposition "
                f"'{case['disposition']}' and a {case['investigation_note_length']}-character "
                f"note -- a legitimately fast, well-documented dismissal, not negligence."
            )
        else:
            explanation = f"No fast_closure anomaly seeded for case {case['case_id']}; ordinary generated closure time."
        rows.append(
            {
                "ground_truth_id": next_id(),
                "entity_id": case["entity_id"],
                "case_id": case["case_id"],
                "asset_id": None,
                "use_case_type": "fast_closure",
                "status": status,
                "explanation": explanation,
            }
        )

    # --- no_escalation: every closed high/critical case ---------------------
    ne_status_by_case = {case["case_id"]: status for case, status in no_escalation_seeded}
    for case in cases:
        if case["status"] != "closed" or case["severity"] not in ("high", "critical"):
            continue
        status = ne_status_by_case.get(case["case_id"], "normal")
        if status == "true_anomaly":
            explanation = (
                f"Seeded: case {case['case_id']} (entity {case['entity_id']}, severity "
                f"{case['severity']}) was forced to non-escalated with no documented "
                f"exception -- severity indicates escalation should have occurred."
            )
        elif status == "false_positive_control":
            explanation = (
                f"Seeded: case {case['case_id']} (entity {case['entity_id']}, severity "
                f"{case['severity']}) is non-escalated, but disposition "
                f"'{case['disposition']}' documents an approved policy exception -- "
                f"legitimate non-escalation, not negligence."
            )
        else:
            explanation = f"No no_escalation anomaly seeded for case {case['case_id']}; ordinary generated escalation behavior."
        rows.append(
            {
                "ground_truth_id": next_id(),
                "entity_id": case["entity_id"],
                "case_id": case["case_id"],
                "asset_id": None,
                "use_case_type": "no_escalation",
                "status": status,
                "explanation": explanation,
            }
        )

    # --- quiet_critical_asset: every critical-tier asset ---------------------
    event_counts = _event_count_by_asset(events)
    critical_assets = [a for a in assets if a["criticality_tier"] == "critical"]
    peer_counts = [event_counts.get(a["asset_id"], 0) for a in critical_assets]
    peer_median = sorted(peer_counts)[len(peer_counts) // 2] if peer_counts else 0

    for asset in critical_assets:
        asset_id = asset["asset_id"]
        count = event_counts.get(asset_id, 0)
        if asset_id in quiet_critical_anomaly_assets:
            status = "true_anomaly"
            explanation = (
                f"Seeded: critical asset {asset_id} ('{asset['asset_name']}', entity "
                f"{asset['entity_id']}) generated only {count} events over the window, "
                f"versus a peer critical-tier median of {peer_median} -- materially "
                f"reduced activity with no documented legitimate reason."
            )
        elif asset_id in quiet_critical_fp_assets:
            status = "false_positive_control"
            explanation = (
                f"Seeded: critical asset {asset_id} ('{asset['asset_name']}', entity "
                f"{asset['entity_id']}) generated only {count} events over the window, "
                f"versus a peer critical-tier median of {peer_median} -- low activity is "
                f"legitimate for this asset's role (e.g. cold-standby), not a monitoring "
                f"gap. NOTE: the currently-specified quiet_critical_asset detector (peer "
                f"event-count comparison only) has no field to distinguish this from the "
                f"true anomaly above -- this is a known, documented limitation, not "
                f"something this generator hides."
            )
        else:
            status = "normal"
            explanation = (
                f"No quiet_critical_asset anomaly seeded for {asset_id}; {count} events "
                f"is ordinary for a critical-tier asset (peer median {peer_median})."
            )
        rows.append(
            {
                "ground_truth_id": next_id(),
                "entity_id": asset["entity_id"],
                "case_id": None,
                "asset_id": asset_id,
                "use_case_type": "quiet_critical_asset",
                "status": status,
                "explanation": explanation,
            }
        )

    return rows
