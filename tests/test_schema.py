"""Structural tests for the canonical SAT-SA schema.

These tests do not exercise any generator or detector logic (neither exists
yet on Day 1). They only confirm that the schema itself is complete, self-
consistent, and capable of representing the three Day-2 detection use cases
and an independent ground-truth table, per the Day 1 rules.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.db.schema import TABLE_NAMES
from src.validation.checks import (
    get_columns,
    get_primary_key_columns,
    table_exists,
    tables_referencing,
)


# ---------------------------------------------------------------------------
# 1. Required tables and columns exist
# ---------------------------------------------------------------------------

def test_all_canonical_tables_exist(conn):
    for table in TABLE_NAMES:
        assert table_exists(conn, table), f"missing table: {table}"


@pytest.mark.parametrize(
    "table,required_columns",
    [
        ("entity", ["entity_id", "entity_name", "sector"]),
        ("asset", ["asset_id", "entity_id", "criticality_tier"]),
        ("case_record", ["case_id", "entity_id", "severity", "opened_at", "closed_at", "status"]),
        ("event", ["event_id", "entity_id", "asset_id", "occurred_at", "severity", "case_id"]),
        ("escalation", ["escalation_id", "case_id", "escalated", "escalation_type", "escalated_at"]),
        (
            "ground_truth",
            ["ground_truth_id", "entity_id", "case_id", "asset_id", "use_case_type", "status", "explanation"],
        ),
    ],
)
def test_required_columns_present(conn, table, required_columns):
    actual = set(get_columns(conn, table))
    missing = set(required_columns) - actual
    assert not missing, f"{table} is missing columns: {missing}"


@pytest.mark.parametrize(
    "table,expected_pk",
    [
        ("entity", ["entity_id"]),
        ("asset", ["asset_id"]),
        ("case_record", ["case_id"]),
        ("event", ["event_id"]),
        ("escalation", ["escalation_id"]),
        ("ground_truth", ["ground_truth_id"]),
    ],
)
def test_primary_keys_defined(conn, table, expected_pk):
    assert get_primary_key_columns(conn, table) == expected_pk


# ---------------------------------------------------------------------------
# 2. IDs behave like IDs (non-null, unique)
# ---------------------------------------------------------------------------

def test_duplicate_primary_key_is_rejected(conn):
    conn.execute(
        "INSERT INTO entity (entity_id, entity_name, sector) VALUES ('ENT-001', 'Alpha Power', 'power');"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO entity (entity_id, entity_name, sector) VALUES ('ENT-001', 'Duplicate', 'power');"
        )


# ---------------------------------------------------------------------------
# 3. Relationships are logically representable end-to-end
# ---------------------------------------------------------------------------

def test_full_relationship_chain_is_insertable(conn):
    """One entity -> one asset -> one event -> one case -> one escalation ->
    one ground_truth row, all linked, with foreign keys enforced (ON)."""

    conn.execute(
        "INSERT INTO entity (entity_id, entity_name, sector) VALUES ('ENT-001', 'Alpha Power', 'power');"
    )
    conn.execute(
        """INSERT INTO asset (asset_id, entity_id, asset_name, criticality_tier)
           VALUES ('AST-001', 'ENT-001', 'SCADA Gateway', 'critical');"""
    )
    conn.execute(
        """INSERT INTO case_record
               (case_id, entity_id, severity, opened_at, closed_at, status, disposition)
           VALUES
               ('CASE-001', 'ENT-001', 'critical', '2026-01-05T10:00:00', '2026-01-05T10:04:00', 'closed', 'confirmed_incident');"""
    )
    conn.execute(
        """INSERT INTO event
               (event_id, entity_id, asset_id, occurred_at, severity, category, case_id)
           VALUES
               ('EVT-001', 'ENT-001', 'AST-001', '2026-01-05T09:58:00', 'critical', 'intrusion_attempt', 'CASE-001');"""
    )
    # case_record.related_event_id is a logical, non-FK-enforced pointer back
    # to the event (see schema.py docstring) — set it after the event exists.
    conn.execute(
        "UPDATE case_record SET related_event_id = 'EVT-001' WHERE case_id = 'CASE-001';"
    )
    conn.execute(
        """INSERT INTO escalation (escalation_id, case_id, escalated, escalation_type, escalated_at)
           VALUES ('ESC-001', 'CASE-001', 0, NULL, NULL);"""
    )
    conn.execute(
        """INSERT INTO ground_truth
               (ground_truth_id, entity_id, case_id, asset_id, use_case_type, status, explanation)
           VALUES
               ('GT-001', 'ENT-001', 'CASE-001', NULL, 'no_escalation',
                'true_anomaly', 'Critical case closed with no escalation record, seeded on purpose.');"""
    )
    conn.commit()

    row = conn.execute(
        """SELECT e.entity_name, a.asset_name, c.case_id, ev.event_id, esc.escalated, gt.status
           FROM ground_truth gt
           JOIN entity e ON e.entity_id = gt.entity_id
           JOIN case_record c ON c.case_id = gt.case_id
           JOIN escalation esc ON esc.case_id = c.case_id
           JOIN event ev ON ev.case_id = c.case_id
           JOIN asset a ON a.asset_id = ev.asset_id
           WHERE gt.ground_truth_id = 'GT-001';"""
    ).fetchone()

    assert row == ("Alpha Power", "SCADA Gateway", "CASE-001", "EVT-001", 0, "true_anomaly")


def test_foreign_keys_are_enforced(conn):
    """A case referencing a nonexistent entity must be rejected outright,
    confirming PRAGMA foreign_keys = ON actually took effect."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO case_record (case_id, entity_id, severity, opened_at, status)
               VALUES ('CASE-999', 'ENT-DOES-NOT-EXIST', 'high', '2026-01-01T00:00:00', 'open');"""
        )


# ---------------------------------------------------------------------------
# 4. Every Day-2 use case has the fields it needs
# ---------------------------------------------------------------------------

def test_fast_closure_use_case_fields_available(conn):
    cols = set(get_columns(conn, "case_record"))
    assert {"entity_id", "severity", "opened_at", "closed_at"}.issubset(cols)


def test_no_escalation_use_case_fields_available(conn):
    case_cols = set(get_columns(conn, "case_record"))
    escalation_cols = set(get_columns(conn, "escalation"))
    assert "severity" in case_cols
    assert {"case_id", "escalated"}.issubset(escalation_cols)


def test_quiet_critical_asset_use_case_fields_available(conn):
    asset_cols = set(get_columns(conn, "asset"))
    event_cols = set(get_columns(conn, "event"))
    assert {"asset_id", "entity_id", "criticality_tier"}.issubset(asset_cols)
    assert {"asset_id", "occurred_at"}.issubset(event_cols)


# ---------------------------------------------------------------------------
# 5. Ground truth is structurally independent of detector-input tables
# ---------------------------------------------------------------------------

def test_ground_truth_is_not_referenced_by_detector_input_tables(conn):
    """No detector-input table (entity, asset, event, case_record, escalation)
    may have a foreign key pointing at ground_truth. If one did, inserting a
    normal operational record could require a ground_truth row to exist
    first, which would make ground truth an implicit input rather than a
    pure post-hoc evaluation table."""
    detector_input_tables = ["entity", "asset", "event", "case_record", "escalation"]
    referencing = tables_referencing(conn, "ground_truth", detector_input_tables)
    assert referencing == [], f"detector-input tables must not reference ground_truth, found: {referencing}"


def test_ground_truth_use_case_type_matches_config_vocabulary(conn):
    from src.config import USE_CASE_TYPES

    conn.execute(
        "INSERT INTO entity (entity_id, entity_name, sector) VALUES ('ENT-002', 'Beta Bank', 'banking');"
    )
    for use_case in USE_CASE_TYPES:
        conn.execute(
            """INSERT INTO ground_truth
                   (ground_truth_id, entity_id, use_case_type, status, explanation)
               VALUES (?, 'ENT-002', ?, 'normal', 'baseline record, no anomaly seeded');""",
            (f"GT-{use_case}", use_case),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM ground_truth;").fetchone()[0]
    assert count == len(USE_CASE_TYPES)


def test_ground_truth_status_vocabulary_matches_config(conn):
    from src.config import GT_STATUSES

    conn.execute(
        "INSERT INTO entity (entity_id, entity_name, sector) VALUES ('ENT-003', 'Gamma Telecom', 'telecom');"
    )
    for status in GT_STATUSES:
        conn.execute(
            """INSERT INTO ground_truth
                   (ground_truth_id, entity_id, use_case_type, status, explanation)
               VALUES (?, 'ENT-003', 'fast_closure', ?, 'exercising status vocabulary in a test');""",
            (f"GT-status-{status}", status),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM ground_truth;").fetchone()[0]
    assert count == len(GT_STATUSES)
