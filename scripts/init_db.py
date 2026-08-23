"""Create (or cleanly rebuild) the SAT-SA SQLite database, load the
generated synthetic dataset, and validate the result.

Day 1D: this script now does the full pipeline -- schema, indexes,
ingestion, and validation -- not just schema creation (see docs/INGESTION.md
for why this replaced the Day 1A schema-only version rather than living
alongside it as a second script).

Safe to rerun: the existing database file is always deleted before
recreating it, so repeated runs never accumulate duplicate rows. This is a
clean-rebuild strategy, not incremental upsert (see docs/INGESTION.md for
why that's the right choice here).

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --db-path db/sat_sa.db --data-dir data/generated
    python scripts/init_db.py --schema-only   # schema + indexes, no data load
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_DB_PATH, GENERATED_DATA_DIR
from src.db.connection import get_connection
from src.db.ingest import load_all
from src.db.indexes import create_indexes
from src.db.schema import TABLE_NAMES, create_all
from src.validation.db_validation import (
    anomaly_counts_by_use_case,
    peer_group_counts,
    row_counts,
    validate_database,
    verify_fast_closure_seeded,
    verify_no_escalation_seeded,
    verify_quiet_critical_asset_seeded,
)


def _print_seeded_verification(conn) -> None:
    print("\n--- direct SQL verification: seeded conditions survived ingestion ---")

    print("\n  fast_closure:")
    for row in verify_fast_closure_seeded(conn):
        print(
            f"    [{row['status']:<24}] {row['case_id']} entity={row['entity_id']} "
            f"severity={row['severity']} closure_minutes={row['closure_minutes']:.1f} "
            f"disposition={row['disposition']} note_len={row['investigation_note_length']}"
        )

    print("\n  no_escalation:")
    for row in verify_no_escalation_seeded(conn):
        print(
            f"    [{row['status']:<24}] {row['case_id']} entity={row['entity_id']} "
            f"severity={row['severity']} escalated={row['escalated']} disposition={row['disposition']}"
        )

    print("\n  quiet_critical_asset:")
    for row in verify_quiet_critical_asset_seeded(conn):
        print(
            f"    [{row['status']:<24}] {row['asset_id']} ('{row['asset_name']}') entity={row['entity_id']} "
            f"event_count={row['event_count']} peer_median={row['peer_median_event_count']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help=f"Path to the SQLite database file. Default: {DEFAULT_DB_PATH}.")
    parser.add_argument("--data-dir", type=Path, default=GENERATED_DATA_DIR, help=f"Directory containing generated CSVs. Default: {GENERATED_DATA_DIR}.")
    parser.add_argument("--schema-only", action="store_true", help="Create schema and indexes only; do not load data.")
    args = parser.parse_args()

    # Clean rebuild: always start from a fresh file so reruns never
    # accumulate duplicate rows.
    if args.db_path.exists():
        args.db_path.unlink()
        print(f"Removed existing database at {args.db_path} (clean rebuild).")

    conn = get_connection(args.db_path)
    create_all(conn)
    create_indexes(conn)

    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';").fetchall()
    }
    missing = [t for t in TABLE_NAMES if t not in existing_tables]
    if missing:
        print(f"ERROR: {len(missing)} table(s) failed to create: {missing}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    print(f"Schema + indexes created at: {args.db_path}")

    if args.schema_only:
        print("`--schema-only` set: skipping data load.")
        conn.close()
        return

    counts = load_all(conn, args.data_dir)
    print("\n--- rows loaded ---")
    for table, count in counts.items():
        print(f"  {table:<14} {count}")

    problems = validate_database(conn)
    if problems:
        print(f"\nDATABASE VALIDATION FAILED -- {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    print("\nDatabase validation: PASSED")

    print("\n--- row counts (post-load, via SQL) ---")
    for table, count in row_counts(conn).items():
        print(f"  {table:<14} {count}")

    print("\n--- peer-group (sector) counts ---")
    for sector, count in peer_group_counts(conn).items():
        print(f"  {sector:<10} {count}")

    print("\n--- ground-truth anomaly counts by use case ---")
    for use_case, statuses in anomaly_counts_by_use_case(conn).items():
        print(
            f"  {use_case:<22} normal={statuses.get('normal', 0):<5} "
            f"true_anomaly={statuses.get('true_anomaly', 0):<3} "
            f"false_positive_control={statuses.get('false_positive_control', 0)}"
        )

    _print_seeded_verification(conn)

    conn.close()
    print("\nDatabase ready.")


if __name__ == "__main__":
    main()
