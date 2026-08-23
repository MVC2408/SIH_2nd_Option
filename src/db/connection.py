"""SQLite connection management.

Deliberately thin: a single function to open a connection with sane
defaults (foreign keys enforced, parent directories created), plus a
convenience function that opens a connection and ensures the schema exists.
Uses pathlib throughout so this works unmodified on Windows and
Linux/macOS (rule: no machine-specific absolute paths).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.schema import create_all


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection at `db_path`, creating parent dirs if needed.

    Foreign key enforcement is turned on explicitly, since SQLite disables
    it by default even when the schema declares FOREIGN KEY constraints.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Open a connection at `db_path` and ensure the canonical schema exists.

    Returns an open connection so callers (scripts, tests) can use it
    immediately without a second round trip.
    """
    conn = get_connection(db_path)
    create_all(conn)
    return conn
