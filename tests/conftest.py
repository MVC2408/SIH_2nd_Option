from __future__ import annotations

import sys
from pathlib import Path

# Allow `import src...` when pytest is run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.connection import get_connection
from src.db.schema import create_all


@pytest.fixture()
def conn(tmp_path):
    """A fresh, schema-initialized SQLite connection backed by a temp file.

    Uses a real file (not :memory:) under tmp_path so behaviour matches the
    real init_db.py script as closely as possible, while never touching the
    project's actual db/sat_sa.db.
    """
    db_path = tmp_path / "test_sat_sa.db"
    connection = get_connection(db_path)
    create_all(connection)
    yield connection
    connection.close()
