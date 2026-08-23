"""Tests for schema/indexes/ingestion/validation of the SQLite database
built from generated CSV data (Day 1D).

Uses a fresh generated dataset (via the pipeline directly, not CLI) written
to a temp directory, then ingested into a temp SQLite file -- mirrors what
scripts/init_db.py does, without touching the real db/ or data/generated/.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.db.connection import get_connection
from src.db.indexes import create_indexes
from src.db.ingest import load_all
from src.db.schema import TABLE_NAMES, create_all
from src.generation.config import GeneratorConfig
from src.generation.pipeline import generate_dataset
from src.generation.writer import write_all
from src.validation.db_validation import (
    anomaly_counts_by_use_case,
    peer_group_counts,
    row_counts,
    validate_database,
    verify_fast_closure_seeded,
    verify_no_escalation_seeded,
    verify_quiet_critical_asset_seeded,
)


@pytest.fixture()
def loaded_db(tmp_path):
    """Generate a real dataset, write it to CSV, load it into a fresh
    SQLite file, and return the open connection."""
    data_dir = tmp_path / "generated"
    config = GeneratorConfig(num_entities=15, seed=321, output_dir=data_dir)
    tables = generate_dataset(config)
    write_all(data_dir, tables)

    db_path = tmp_path / "test_sat_sa.db"
    conn = get_connection(db_path)
    create_all(conn)
    create_indexes(conn)
    load_all(conn, data_dir)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Database / schema creation
# ---------------------------------------------------------------------------

def test_all_tables_created(loaded_db):
    existing = {
        row[0] for row in loaded_db.execute("SELECT name FROM sqlite_master WHERE type = 'table';").fetchall()
    }
    for table in TABLE_NAMES:
        assert table in existing


def test_indexes_created(loaded_db):
    existing_indexes = {
        row[0] for row in loaded_db.execute("SELECT name FROM sqlite_master WHERE type = 'index';").fetchall()
    }
    assert "idx_entity_sector" in existing_indexes
    assert "idx_case_severity_status" in existing_indexes
    assert "idx_asset_criticality_tier" in existing_indexes
    assert "idx_ground_truth_use_case_status" in existing_indexes


def test_foreign_keys_are_enforced(loaded_db):
    with pytest.raises(sqlite3.IntegrityError):
        loaded_db.execute(
            "INSERT INTO asset (asset_id, entity_id, asset_name, criticality_tier) "
            "VALUES ('AST-BOGUS', 'ENT-DOES-NOT-EXIST', 'Fake Asset', 'critical');"
        )


# ---------------------------------------------------------------------------
# Ingestion / row counts
# ---------------------------------------------------------------------------

def test_row_counts_match_generated_dataset(tmp_path, loaded_db):
    counts = row_counts(loaded_db)
    assert counts["entity"] == 15
    assert counts["asset"] > 0
    assert counts["event"] > 0
    assert counts["case_record"] > 0
    assert counts["escalation"] == counts["case_record"]  # one escalation row per case, by construction
    assert counts["ground_truth"] > 0


def test_no_derived_closure_duration_column_exists(loaded_db):
    """Rule: closure duration must be derivable, not stored. Confirm
    case_record has no such column."""
    columns = {row[1] for row in loaded_db.execute("PRAGMA table_info(case_record);").fetchall()}
    assert "closure_duration" not in columns
    assert "closure_minutes" not in columns


# ---------------------------------------------------------------------------
# Post-ingestion validation
# ---------------------------------------------------------------------------

def test_validate_database_passes_on_clean_load(loaded_db):
    problems = validate_database(loaded_db)
    assert problems == []


def test_validate_database_catches_dangling_reference(loaded_db):
    # Sabotage: point one event at a nonexistent entity by going around the
    # FK constraint (disable enforcement just for this destructive test).
    loaded_db.execute("PRAGMA foreign_keys = OFF;")
    case_id = loaded_db.execute("SELECT case_id FROM case_record LIMIT 1;").fetchone()[0]
    loaded_db.execute("UPDATE case_record SET entity_id = 'ENT-GHOST' WHERE case_id = ?;", (case_id,))
    loaded_db.commit()

    problems = validate_database(loaded_db)
    assert any("nonexistent entity" in p for p in problems)


def test_validate_database_flags_entity_count_outside_15_20(tmp_path):
    data_dir = tmp_path / "generated_small"
    config = GeneratorConfig(num_entities=12, seed=5, output_dir=data_dir)
    tables = generate_dataset(config)
    write_all(data_dir, tables)

    db_path = tmp_path / "small.db"
    conn = get_connection(db_path)
    create_all(conn)
    create_indexes(conn)
    load_all(conn, data_dir)

    problems = validate_database(conn)
    assert any("expected 15-20" in p for p in problems)
    conn.close()


# ---------------------------------------------------------------------------
# Seeded anomaly / false-positive-control presence, via direct SQL
# ---------------------------------------------------------------------------

def test_fast_closure_seeded_conditions_survive_ingestion(loaded_db):
    rows = verify_fast_closure_seeded(loaded_db)
    statuses = {r["status"] for r in rows}
    assert "true_anomaly" in statuses
    assert "false_positive_control" in statuses
    true_anomalies = [r for r in rows if r["status"] == "true_anomaly"]
    for r in true_anomalies:
        assert r["closure_minutes"] < 15  # forced fast, per model.FAST_CLOSURE_ANOMALY_MINUTES_RANGE


def test_no_escalation_seeded_conditions_survive_ingestion(loaded_db):
    rows = verify_no_escalation_seeded(loaded_db)
    statuses = {r["status"] for r in rows}
    assert "true_anomaly" in statuses
    assert "false_positive_control" in statuses
    for r in rows:
        assert r["escalated"] == 0  # both anomaly and control are non-escalated by construction


def test_quiet_critical_asset_seeded_conditions_survive_ingestion(loaded_db):
    rows = verify_quiet_critical_asset_seeded(loaded_db)
    statuses = {r["status"] for r in rows}
    assert "true_anomaly" in statuses
    assert "false_positive_control" in statuses
    for r in rows:
        assert r["event_count"] < r["peer_median_event_count"]


def test_anomaly_counts_by_use_case_matches_ground_truth(loaded_db):
    counts = anomaly_counts_by_use_case(loaded_db)
    for use_case in ("fast_closure", "no_escalation", "quiet_critical_asset"):
        assert counts[use_case]["true_anomaly"] >= 1
        assert counts[use_case]["false_positive_control"] >= 1


def test_peer_group_counts_reported(loaded_db):
    counts = peer_group_counts(loaded_db)
    assert set(counts.keys()) == {"power", "banking", "telecom"}
    for count in counts.values():
        assert count >= 4


# ---------------------------------------------------------------------------
# Rerun / clean-rebuild behavior (no duplicate accumulation)
# ---------------------------------------------------------------------------

def test_reloading_into_a_freshly_recreated_db_does_not_duplicate_rows(tmp_path):
    data_dir = tmp_path / "generated"
    config = GeneratorConfig(num_entities=15, seed=555, output_dir=data_dir)
    tables = generate_dataset(config)
    write_all(data_dir, tables)

    db_path = tmp_path / "rebuild.db"

    def build_fresh():
        if db_path.exists():
            db_path.unlink()
        conn = get_connection(db_path)
        create_all(conn)
        create_indexes(conn)
        load_all(conn, data_dir)
        counts = row_counts(conn)
        conn.close()
        return counts

    counts_1 = build_fresh()
    counts_2 = build_fresh()
    assert counts_1 == counts_2


def test_loading_twice_into_the_same_db_without_rebuild_raises_integrity_error(tmp_path):
    """Confirms load_all does NOT silently upsert -- loading into an
    already-populated table must fail loudly (duplicate primary keys),
    which is exactly why scripts/init_db.py always deletes the file first."""
    data_dir = tmp_path / "generated"
    config = GeneratorConfig(num_entities=15, seed=777, output_dir=data_dir)
    tables = generate_dataset(config)
    write_all(data_dir, tables)

    db_path = tmp_path / "no_rebuild.db"
    conn = get_connection(db_path)
    create_all(conn)
    load_all(conn, data_dir)

    with pytest.raises(sqlite3.IntegrityError):
        load_all(conn, data_dir)
    conn.close()
