"""Load generated CSV data into the SQLite schema.

Loads in FK-safe order (src.db.schema.TABLE_NAMES is already ordered this
way: entity -> asset -> case_record -> event -> escalation -> ground_truth).
No derived fields are computed or stored here -- e.g. closure duration is
never written to a column; it stays derivable from case_record.opened_at /
closed_at at query time, per the project rule to keep source data
authoritative (see docs/INGESTION.md).

This module assumes a CLEAN schema (freshly created, empty tables). It does
not attempt to upsert or de-duplicate -- see scripts/init_db.py, which
always deletes and recreates the database file before calling this, so
re-running never appends duplicates.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.generation.writer import TABLE_FILENAMES

# Column order per table, and a converter for any column that isn't a plain
# string (CSV always produces strings; empty string means NULL for optional
# columns -- converted to None before the type converter runs, if any).
_TABLE_COLUMNS: dict[str, list[str]] = {
    "entity": ["entity_id", "entity_name", "entity_type", "sector", "notes"],
    "asset": ["asset_id", "entity_id", "asset_name", "criticality_tier"],
    "case_record": [
        "case_id", "entity_id", "related_event_id", "severity", "opened_at",
        "closed_at", "status", "disposition", "investigation_note_length",
    ],
    "event": ["event_id", "entity_id", "asset_id", "occurred_at", "severity", "category", "case_id"],
    "escalation": ["escalation_id", "case_id", "escalated", "escalation_type", "escalated_at"],
    "ground_truth": ["ground_truth_id", "entity_id", "case_id", "asset_id", "use_case_type", "status", "explanation"],
}

_TABLE_CONVERTERS: dict[str, dict[str, type]] = {
    "case_record": {"investigation_note_length": int},
    "escalation": {"escalated": int},
}

# Load order must respect foreign keys: entity/asset before case_record,
# case_record before event (event.case_id references it) and escalation
# (escalation.case_id references it), and all four before ground_truth.
LOAD_ORDER: tuple[str, ...] = ("entity", "asset", "case_record", "event", "escalation", "ground_truth")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"expected generated data file not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_table(conn: sqlite3.Connection, table_name: str, csv_path: Path) -> int:
    """Load one CSV file into one table. Returns the number of rows inserted."""
    columns = _TABLE_COLUMNS[table_name]
    converters = _TABLE_CONVERTERS.get(table_name, {})
    rows = _read_csv_rows(csv_path)
    if not rows:
        return 0

    values = []
    for row in rows:
        record = []
        for col in columns:
            raw = row.get(col, "")
            val = None if raw == "" else raw
            if val is not None and col in converters:
                val = converters[col](val)
            record.append(val)
        values.append(tuple(record))

    placeholders = ",".join(["?"] * len(columns))
    conn.executemany(
        f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders});",
        values,
    )
    conn.commit()
    return len(values)


def load_all(conn: sqlite3.Connection, data_dir: Path) -> dict[str, int]:
    """Load every table from `data_dir` (the generator's CSV output
    directory) into `conn`, in FK-safe order. Returns {table_name: row_count}."""
    counts: dict[str, int] = {}
    for table_name in LOAD_ORDER:
        csv_path = data_dir / TABLE_FILENAMES[table_name]
        counts[table_name] = load_table(conn, table_name, csv_path)
    return counts
