"""Post-ingestion validation for the SQLite database.

Two distinct jobs, kept separate:

1. `validate_database` -- structural/quality checks via direct SQL queries
   against the already-loaded database (row counts, FK sanity, required
   metadata, peer-group sizes). Returns a list of problem strings; empty
   means pass.

2. `verify_seeded_*` functions -- direct SQL proof that the three seeded
   anomaly classes and their false-positive controls actually survived
   ingestion, by joining ground_truth back to the operational tables and
   returning the real observed values. This is NOT a detector -- it uses
   ground_truth directly, which is fine here because the point of this
   step is to confirm the *data* made it through ingestion correctly, not
   to detect anything blind. Day 2 detectors must still never read
   ground_truth (see src/detection/fast_closure.py).
"""

from __future__ import annotations

import sqlite3
import statistics


# ---------------------------------------------------------------------------
# 1. Structural / quality validation
# ---------------------------------------------------------------------------

def validate_database(conn: sqlite3.Connection) -> list[str]:
    problems: list[str] = []

    # --- entities ------------------------------------------------------
    entity_count = conn.execute("SELECT COUNT(*) FROM entity;").fetchone()[0]
    if not (15 <= entity_count <= 20):
        problems.append(f"entity count = {entity_count}, expected 15-20")

    distinct_entity_ids = conn.execute("SELECT COUNT(DISTINCT entity_id) FROM entity;").fetchone()[0]
    if distinct_entity_ids != entity_count:
        problems.append(f"entity_id is not unique: {entity_count} rows but {distinct_entity_ids} distinct ids")

    missing_metadata = conn.execute(
        "SELECT COUNT(*) FROM entity WHERE entity_name IS NULL OR sector IS NULL;"
    ).fetchone()[0]
    if missing_metadata:
        problems.append(f"{missing_metadata} entity row(s) missing required metadata (entity_name/sector)")

    # --- events ----------------------------------------------------------
    bad_event_entity_refs = conn.execute(
        """SELECT COUNT(*) FROM event ev
           LEFT JOIN entity e ON e.entity_id = ev.entity_id
           WHERE e.entity_id IS NULL;"""
    ).fetchone()[0]
    if bad_event_entity_refs:
        problems.append(f"{bad_event_entity_refs} event row(s) reference a nonexistent entity")

    bad_event_severity = conn.execute(
        "SELECT COUNT(*) FROM event WHERE severity NOT IN ('low','medium','high','critical');"
    ).fetchone()[0]
    if bad_event_severity:
        problems.append(f"{bad_event_severity} event row(s) have an invalid severity value")

    null_event_timestamp = conn.execute("SELECT COUNT(*) FROM event WHERE occurred_at IS NULL;").fetchone()[0]
    if null_event_timestamp:
        problems.append(f"{null_event_timestamp} event row(s) missing occurred_at")

    # --- cases -------------------------------------------------------------
    bad_case_entity_refs = conn.execute(
        """SELECT COUNT(*) FROM case_record c
           LEFT JOIN entity e ON e.entity_id = c.entity_id
           WHERE e.entity_id IS NULL;"""
    ).fetchone()[0]
    if bad_case_entity_refs:
        problems.append(f"{bad_case_entity_refs} case_record row(s) reference a nonexistent entity")

    bad_closure_relationship = conn.execute(
        """SELECT COUNT(*) FROM case_record
           WHERE status = 'closed' AND (closed_at IS NULL OR closed_at <= opened_at);"""
    ).fetchone()[0]
    if bad_closure_relationship:
        problems.append(
            f"{bad_closure_relationship} closed case_record row(s) have closed_at missing or not after opened_at"
        )

    open_with_closed_at = conn.execute(
        "SELECT COUNT(*) FROM case_record WHERE status = 'open' AND closed_at IS NOT NULL;"
    ).fetchone()[0]
    if open_with_closed_at:
        problems.append(f"{open_with_closed_at} open case_record row(s) have a closed_at set")

    # --- escalations ---------------------------------------------------
    bad_escalation_case_refs = conn.execute(
        """SELECT COUNT(*) FROM escalation esc
           LEFT JOIN case_record c ON c.case_id = esc.case_id
           WHERE c.case_id IS NULL;"""
    ).fetchone()[0]
    if bad_escalation_case_refs:
        problems.append(f"{bad_escalation_case_refs} escalation row(s) reference a nonexistent case_record")

    bad_escalation_flag = conn.execute(
        "SELECT COUNT(*) FROM escalation WHERE escalated NOT IN (0, 1);"
    ).fetchone()[0]
    if bad_escalation_flag:
        problems.append(f"{bad_escalation_flag} escalation row(s) have an invalid escalated value")

    inconsistent_escalated_at = conn.execute(
        "SELECT COUNT(*) FROM escalation WHERE escalated = 1 AND escalated_at IS NULL;"
    ).fetchone()[0]
    if inconsistent_escalated_at:
        problems.append(f"{inconsistent_escalated_at} escalation row(s) have escalated=1 but no escalated_at")

    # --- ground truth: seeded anomalies / controls present ------------------
    for use_case in ("fast_closure", "no_escalation", "quiet_critical_asset"):
        anomaly_count = conn.execute(
            "SELECT COUNT(*) FROM ground_truth WHERE use_case_type = ? AND status = 'true_anomaly';",
            (use_case,),
        ).fetchone()[0]
        if anomaly_count == 0:
            problems.append(f"no true_anomaly ground_truth rows found for use_case '{use_case}'")

        control_count = conn.execute(
            "SELECT COUNT(*) FROM ground_truth WHERE use_case_type = ? AND status = 'false_positive_control';",
            (use_case,),
        ).fetchone()[0]
        if control_count == 0:
            problems.append(f"no false_positive_control ground_truth rows found for use_case '{use_case}'")

    bad_gt_entity_refs = conn.execute(
        """SELECT COUNT(*) FROM ground_truth gt
           LEFT JOIN entity e ON e.entity_id = gt.entity_id
           WHERE e.entity_id IS NULL;"""
    ).fetchone()[0]
    if bad_gt_entity_refs:
        problems.append(f"{bad_gt_entity_refs} ground_truth row(s) reference a nonexistent entity")

    # --- peer groups ---------------------------------------------------
    sector_rows = conn.execute("SELECT sector, COUNT(*) FROM entity GROUP BY sector;").fetchall()
    if not sector_rows:
        problems.append("no peer groups (sectors) found at all")
    for sector, count in sector_rows:
        if count < 4:
            problems.append(f"peer group (sector) '{sector}' has only {count} entities; need >= 4")

    critical_asset_count = conn.execute(
        "SELECT COUNT(*) FROM asset WHERE criticality_tier = 'critical';"
    ).fetchone()[0]
    if critical_asset_count < 4:
        problems.append(f"only {critical_asset_count} critical-tier assets exist; need >= 4 for a meaningful peer baseline")

    return problems


# ---------------------------------------------------------------------------
# 2. Direct SQL proof that seeded conditions survived ingestion
# ---------------------------------------------------------------------------

def verify_fast_closure_seeded(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT gt.status, c.case_id, c.entity_id, c.severity, c.opened_at, c.closed_at,
               c.disposition, c.investigation_note_length,
               (julianday(c.closed_at) - julianday(c.opened_at)) * 24 * 60 AS closure_minutes
        FROM ground_truth gt
        JOIN case_record c ON c.case_id = gt.case_id
        WHERE gt.use_case_type = 'fast_closure' AND gt.status IN ('true_anomaly', 'false_positive_control')
        ORDER BY gt.status, c.case_id;
        """
    ).fetchall()
    columns = ["status", "case_id", "entity_id", "severity", "opened_at", "closed_at", "disposition", "investigation_note_length", "closure_minutes"]
    return [dict(zip(columns, row)) for row in rows]


def verify_no_escalation_seeded(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT gt.status, c.case_id, c.entity_id, c.severity, c.disposition, esc.escalated
        FROM ground_truth gt
        JOIN case_record c ON c.case_id = gt.case_id
        JOIN escalation esc ON esc.case_id = c.case_id
        WHERE gt.use_case_type = 'no_escalation' AND gt.status IN ('true_anomaly', 'false_positive_control')
        ORDER BY gt.status, c.case_id;
        """
    ).fetchall()
    columns = ["status", "case_id", "entity_id", "severity", "disposition", "escalated"]
    return [dict(zip(columns, row)) for row in rows]


def verify_quiet_critical_asset_seeded(conn: sqlite3.Connection) -> list[dict]:
    # Peer median computed over ALL critical-tier assets' event counts.
    peer_rows = conn.execute(
        """
        SELECT a.asset_id, COUNT(ev.event_id) AS event_count
        FROM asset a
        LEFT JOIN event ev ON ev.asset_id = a.asset_id
        WHERE a.criticality_tier = 'critical'
        GROUP BY a.asset_id;
        """
    ).fetchall()
    peer_counts = [count for _asset_id, count in peer_rows]
    peer_median = statistics.median(peer_counts) if peer_counts else 0

    seeded_rows = conn.execute(
        """
        SELECT gt.status, a.asset_id, a.entity_id, a.asset_name,
               COUNT(ev.event_id) AS event_count
        FROM ground_truth gt
        JOIN asset a ON a.asset_id = gt.asset_id
        LEFT JOIN event ev ON ev.asset_id = a.asset_id
        WHERE gt.use_case_type = 'quiet_critical_asset' AND gt.status IN ('true_anomaly', 'false_positive_control')
        GROUP BY gt.ground_truth_id, a.asset_id, a.entity_id, a.asset_name, gt.status
        ORDER BY gt.status, a.asset_id;
        """
    ).fetchall()
    results = []
    for status, asset_id, entity_id, asset_name, event_count in seeded_rows:
        results.append(
            {
                "status": status,
                "asset_id": asset_id,
                "entity_id": entity_id,
                "asset_name": asset_name,
                "event_count": event_count,
                "peer_median_event_count": peer_median,
            }
        )
    return results


# ---------------------------------------------------------------------------
# 3. Row-count / summary report
# ---------------------------------------------------------------------------

def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ("entity", "asset", "case_record", "event", "escalation", "ground_truth")
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0] for t in tables}


def anomaly_counts_by_use_case(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    result = {}
    for use_case in ("fast_closure", "no_escalation", "quiet_critical_asset"):
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM ground_truth WHERE use_case_type = ? GROUP BY status;",
            (use_case,),
        ).fetchall()
        result[use_case] = {status: count for status, count in rows}
    return result


def peer_group_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT sector, COUNT(*) FROM entity GROUP BY sector ORDER BY sector;").fetchall()
    return dict(rows)
