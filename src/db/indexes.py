"""Indexes for the SAT-SA schema.

Deliberately separate from schema.py's table definitions -- indexes are a
query-performance concern, not a data-model concern, and this project's
rule is "create only useful indexes for the future Day 2 workload," not
"index everything."

Each index is justified below by which Day 2 query pattern it serves.
`escalation.case_id` already has an implicit index from its UNIQUE
constraint in schema.py, so no separate index is created for it here.
"""

from __future__ import annotations

import sqlite3

INDEX_STATEMENTS: tuple[str, ...] = (
    # fast_closure / no_escalation: peer grouping is by entity.sector, and
    # detectors join case_record -> entity on entity_id, then filter by
    # case_record.status/severity.
    "CREATE INDEX IF NOT EXISTS idx_entity_sector ON entity (sector);",
    "CREATE INDEX IF NOT EXISTS idx_case_entity_id ON case_record (entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_case_severity_status ON case_record (severity, status);",
    # quiet_critical_asset: peer grouping is by asset.criticality_tier
    # (across ALL entities, not sector-scoped -- see docs/ARCHITECTURE.md),
    # and event counts are aggregated per asset_id.
    "CREATE INDEX IF NOT EXISTS idx_asset_entity_id ON asset (entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_asset_criticality_tier ON asset (criticality_tier);",
    "CREATE INDEX IF NOT EXISTS idx_event_asset_id ON event (asset_id);",
    "CREATE INDEX IF NOT EXISTS idx_event_entity_id ON event (entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_event_occurred_at ON event (occurred_at);",
    # ground_truth: evaluation queries filter by (use_case_type, status),
    # e.g. "give me every true_anomaly for fast_closure".
    "CREATE INDEX IF NOT EXISTS idx_ground_truth_use_case_status ON ground_truth (use_case_type, status);",
)


def create_indexes(conn: sqlite3.Connection) -> None:
    """Create every index if it does not already exist. Idempotent, like
    schema.create_all -- safe to call on every script run."""
    cursor = conn.cursor()
    for statement in INDEX_STATEMENTS:
        cursor.execute(statement)
    conn.commit()
