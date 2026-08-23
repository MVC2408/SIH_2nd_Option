"""Tests for the fast-closure detector (Day 1B Go/No-Go experiment).

Uses the shared `conn` fixture from tests/conftest.py (fresh, schema-
initialized SQLite file per test) and the fixed dataset from
src/experiments/go_no_go_fixture.py.
"""

from __future__ import annotations

import inspect

from src.detection import fast_closure as fast_closure_module
from src.detection.fast_closure import detect_fast_closure
from src.experiments.go_no_go_fixture import build as build_fixture
from src.validation.evaluation import evaluate


def test_obvious_seeded_anomaly_is_detected(conn):
    build_fixture(conn)
    findings = detect_fast_closure(conn)
    detected_case_ids = {f.case_id for f in findings}
    assert "CASE-P05" in detected_case_ids


def test_normal_peer_cases_are_not_flagged(conn):
    build_fixture(conn)
    findings = detect_fast_closure(conn)
    detected_case_ids = {f.case_id for f in findings}
    normal_case_ids = {"CASE-P01", "CASE-P02", "CASE-P03", "CASE-P04"}
    assert not (normal_case_ids & detected_case_ids), (
        f"normal cases wrongly flagged: {normal_case_ids & detected_case_ids}"
    )


def test_false_positive_control_is_flagged_by_this_minimal_detector(conn):
    """Documents known, expected behavior: a closure-duration-only detector
    cannot distinguish a legitimately fast, well-documented dismissal from
    genuine negligence -- it has no access to disposition/note-length yet.
    This is NOT a bug to hide; it's the reason Day 2's corroboration-based
    scoring (see project roadmap, Section 12) exists. If this test starts
    failing because the control stops being flagged, that's a real, welcome
    improvement and this test (and its docstring) should be updated to say so."""
    build_fixture(conn)
    findings = detect_fast_closure(conn)
    detected_case_ids = {f.case_id for f in findings}
    assert "CASE-P06" in detected_case_ids


def test_finding_contains_full_explanation_fields(conn):
    build_fixture(conn)
    findings = detect_fast_closure(conn)
    finding = next(f for f in findings if f.case_id == "CASE-P05")

    assert finding.entity_id == "ENT-P05"
    assert finding.detection_type == "fast_closure"
    assert finding.observed_closure_minutes < finding.lower_fence_minutes
    assert finding.peer_group_size >= 2
    assert finding.reason  # non-empty, human-readable


def test_detector_does_not_depend_on_ground_truth_table(conn):
    """Structural proof, not just a convention: delete every ground_truth
    row (the detector's input tables are untouched) and confirm detection
    output is identical."""
    build_fixture(conn)
    findings_before = {f.case_id for f in detect_fast_closure(conn)}

    conn.execute("DELETE FROM ground_truth;")
    conn.commit()

    findings_after = {f.case_id for f in detect_fast_closure(conn)}
    assert findings_before == findings_after


def test_detector_source_has_no_hardcoded_experiment_ids():
    """Rule: do not hard-code the anomaly's entity/case ID in detector logic.
    Enforced structurally by scanning the actual source, not just by
    reviewing it once."""
    source = inspect.getsource(fast_closure_module)
    for forbidden in ("ENT-P05", "CASE-P05", "ENT-P06", "CASE-P06", "ENT-P01", "CASE-P01"):
        assert forbidden not in source, f"detector source references fixture-specific id: {forbidden}"


def test_detector_source_never_queries_ground_truth():
    """The module docstring is allowed to mention 'ground_truth' by name
    (it documents the separation rule); what must never appear is a query
    pattern that would actually touch the table."""
    source = inspect.getsource(fast_closure_module)
    for forbidden_pattern in ("FROM ground_truth", "JOIN ground_truth", "ground_truth."):
        assert forbidden_pattern not in source, f"detector queries ground_truth via: {forbidden_pattern!r}"


def test_results_are_deterministic_across_two_independent_builds(conn, tmp_path):
    """Build the fixture into two entirely separate connections and confirm
    identical output -- reproducibility, not just repeatability within one
    connection."""
    import sqlite3

    from src.db.connection import get_connection
    from src.db.schema import create_all

    build_fixture(conn)
    findings_a = sorted(
        (f.case_id, f.observed_closure_minutes, f.peer_baseline_median_minutes, f.lower_fence_minutes)
        for f in detect_fast_closure(conn)
    )

    second_db_path = tmp_path / "second_test_sat_sa.db"
    conn_b = get_connection(second_db_path)
    create_all(conn_b)
    build_fixture(conn_b)
    findings_b = sorted(
        (f.case_id, f.observed_closure_minutes, f.peer_baseline_median_minutes, f.lower_fence_minutes)
        for f in detect_fast_closure(conn_b)
    )
    conn_b.close()

    assert findings_a == findings_b


def test_evaluation_correctly_separates_anomaly_missed_and_unexpected(conn):
    build_fixture(conn)
    findings = detect_fast_closure(conn)
    detected_case_ids = {f.case_id for f in findings}

    result = evaluate(conn, detected_case_ids, use_case_type="fast_closure")

    assert result.expected_anomaly_case_ids == {"CASE-P05"}
    assert result.correctly_detected == {"CASE-P05"}
    assert result.missed == set()
    assert result.unexpected == set()  # nothing flagged outside seeded anomaly + control
    assert result.false_positive_control_case_ids == {"CASE-P06"}
    assert result.false_positive_controls_flagged == {"CASE-P06"}
