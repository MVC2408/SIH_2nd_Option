"""Structural validation helpers for the SAT-SA SQLite schema.

Pure introspection functions over `sqlite_master` / `PRAGMA table_info` /
`PRAGMA foreign_key_list`. No opinions about data content — that's the
generator's and detectors' job once they exist. These are used by
tests/test_schema.py and are safe to reuse later from scripts.
"""

from __future__ import annotations

import sqlite3


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?;",
        (table_name,),
    ).fetchone()
    return row is not None


def get_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Return column names for `table_name`, in schema order."""
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return [row[1] for row in rows]  # row[1] = column name


def get_primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    # row[5] = pk flag (0 if not part of PK, 1+ = position in composite PK)
    return [row[1] for row in rows if row[5] > 0]


def get_foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[tuple[str, str, str]]:
    """Return (from_column, to_table, to_column) triples for `table_name`."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name});").fetchall()
    # row layout: id, seq, table, from, to, on_update, on_delete, match
    return [(row[3], row[2], row[4]) for row in rows]


def tables_referencing(conn: sqlite3.Connection, target_table: str, all_tables: list[str]) -> list[str]:
    """Return every table (from `all_tables`) that has a foreign key pointing at `target_table`."""
    referencing = []
    for table in all_tables:
        for _from_col, to_table, _to_col in get_foreign_keys(conn, table):
            if to_table == target_table:
                referencing.append(table)
                break
    return referencing
