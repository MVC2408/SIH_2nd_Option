"""Create (or verify) the SAT-SA SQLite database with the canonical schema.

Day 1 scope: this script only creates tables. It does not generate or load
any data — that's a separate script planned for hours 4-6 of Day 1.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --db-path some/other/path.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/init_db.py` from the project root without
# installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_DB_PATH
from src.db.connection import init_db
from src.db.schema import TABLE_NAMES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()

    conn = init_db(args.db_path)
    try:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table';"
            ).fetchall()
        }
    finally:
        conn.close()

    print(f"Database ready at: {args.db_path}")
    print("Tables:")
    for name in TABLE_NAMES:
        status = "OK" if name in existing else "MISSING"
        print(f"  - {name:<15} [{status}]")

    missing = [name for name in TABLE_NAMES if name not in existing]
    if missing:
        print(f"\nERROR: {len(missing)} table(s) failed to create: {missing}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
