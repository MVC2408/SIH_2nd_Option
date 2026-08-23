"""Canonical SAT-SA data model, expressed as SQLite DDL.

Design notes (see docs/ARCHITECTURE.md for the full rationale):

- Six tables: entity, asset, event, case, escalation, ground_truth.
- `entity.sector` doubles as the peer-group key. Detection compares an
  entity/asset against others sharing the same sector rather than against
  the entire population — see "Peer groups" in docs/ARCHITECTURE.md.
- `event` and `case` reference each other conceptually (an event can lead to
  a case; a case is normally triggered by an event), which would form a
  circular foreign key if both directions were enforced at the database
  level. To keep the schema simple and avoid a circular FK, only
  `event.case_id -> case.case_id` is an enforced foreign key.
  `case.related_event_id` is a plain column: a *logical* pointer back to the
  triggering event, intentionally not FK-enforced. This is documented here
  so future readers don't "fix" it into a circular constraint.
- `ground_truth` is a separate table, not a column bolted onto `case` or
  `event`. This is deliberate and required by project rules 18-19: ground
  truth must never be an input to detection logic, only used to evaluate
  detector output afterwards. Keeping it in its own table with no detector
  code reading from it makes that separation structurally obvious, not just
  a convention someone has to remember.
"""

from __future__ import annotations

import sqlite3

# Each statement is a standalone CREATE TABLE, executed in this order so that
# foreign-key targets already exist when referenced.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS entity (
        entity_id     TEXT PRIMARY KEY,
        entity_name   TEXT NOT NULL,
        entity_type   TEXT NOT NULL DEFAULT 'CSE',
        sector        TEXT NOT NULL,   -- peer-group key, e.g. 'power', 'banking', 'telecom'
        notes         TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS asset (
        asset_id          TEXT PRIMARY KEY,
        entity_id         TEXT NOT NULL,
        asset_name        TEXT NOT NULL,
        criticality_tier  TEXT NOT NULL CHECK (criticality_tier IN ('low','medium','high','critical')),
        FOREIGN KEY (entity_id) REFERENCES entity (entity_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS case_record (
        case_id                    TEXT PRIMARY KEY,
        entity_id                  TEXT NOT NULL,
        related_event_id           TEXT,   -- logical reference to event.event_id; NOT FK-enforced, see module docstring
        severity                   TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
        opened_at                  TEXT NOT NULL,   -- ISO 8601 timestamp
        closed_at                  TEXT,            -- ISO 8601 timestamp, NULL while still open
        status                     TEXT NOT NULL CHECK (status IN ('open','closed')),
        disposition                TEXT,            -- e.g. 'confirmed_incident', 'false_positive_dismissed'
        investigation_note_length  INTEGER,         -- proxy for investigation depth; groundwork for a later use case, unused by Day 1/2 detectors
        FOREIGN KEY (entity_id) REFERENCES entity (entity_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS event (
        event_id     TEXT PRIMARY KEY,
        entity_id    TEXT NOT NULL,
        asset_id     TEXT,            -- nullable: not every alert is tied to a known inventoried asset
        occurred_at  TEXT NOT NULL,   -- ISO 8601 timestamp
        severity     TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
        category     TEXT NOT NULL,   -- generator-defined alert category, e.g. 'intrusion_attempt'
        case_id      TEXT,            -- nullable: not every raw event is escalated into a case
        FOREIGN KEY (entity_id) REFERENCES entity (entity_id),
        FOREIGN KEY (asset_id) REFERENCES asset (asset_id),
        FOREIGN KEY (case_id) REFERENCES case_record (case_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS escalation (
        escalation_id   TEXT PRIMARY KEY,
        case_id         TEXT NOT NULL UNIQUE,   -- at most one escalation record per case
        escalated       INTEGER NOT NULL CHECK (escalated IN (0, 1)),
        escalation_type TEXT,        -- nullable, e.g. 'tier2_handoff'; only meaningful when escalated = 1
        escalated_at    TEXT,        -- nullable ISO 8601 timestamp; only meaningful when escalated = 1
        FOREIGN KEY (case_id) REFERENCES case_record (case_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ground_truth (
        ground_truth_id  TEXT PRIMARY KEY,
        entity_id        TEXT NOT NULL,
        case_id          TEXT,   -- nullable: case-scoped use cases (fast_closure, no_escalation) set this
        asset_id         TEXT,   -- nullable: asset-scoped use cases (quiet_critical_asset) set this
        use_case_type    TEXT NOT NULL CHECK (use_case_type IN ('fast_closure', 'no_escalation', 'quiet_critical_asset')),
        status           TEXT NOT NULL CHECK (status IN ('normal', 'true_anomaly', 'false_positive_control')),
        explanation      TEXT NOT NULL,   -- human-readable reason a human could audit; required, never blank
        FOREIGN KEY (entity_id) REFERENCES entity (entity_id),
        FOREIGN KEY (case_id) REFERENCES case_record (case_id),
        FOREIGN KEY (asset_id) REFERENCES asset (asset_id)
    );
    """,
)

# Table names in creation order, used by tests/scripts that need to introspect
# or reset the schema without re-parsing the SQL strings above.
TABLE_NAMES: tuple[str, ...] = (
    "entity",
    "asset",
    "case_record",
    "event",
    "escalation",
    "ground_truth",
)


def create_all(conn: sqlite3.Connection) -> None:
    """Create every SAT-SA table if it does not already exist.

    Idempotent: safe to call against an existing database (e.g. on every
    script run) without losing data, since every statement uses
    ``CREATE TABLE IF NOT EXISTS``.
    """
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    for statement in SCHEMA_STATEMENTS:
        cursor.executescript(statement)
    conn.commit()
