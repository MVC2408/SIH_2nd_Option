"""Day 1B -- Go/No-Go experiment for the FAST CLOSURE detection signal.

Builds a tiny, fully deterministic dataset (src/experiments/go_no_go_fixture.py)
against the LOCKED canonical schema, runs the reusable fast-closure detector
(src/detection/fast_closure.py) WITHOUT ground truth, then separately
evaluates the findings against ground truth (src/validation/evaluation.py).

Runs the whole pipeline twice, independently, to demonstrate reproducibility,
then persists one inspectable copy to db/go_no_go.db.

Usage:
    python scripts/go_no_go_fast_closure.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_DB_PATH
from src.db.schema import create_all
from src.detection.fast_closure import detect_fast_closure
from src.experiments.go_no_go_fixture import build as build_fixture
from src.validation.evaluation import evaluate


def run_once():
    """Build the fixture in a fresh in-memory DB, detect, evaluate. Returns (findings, EvaluationResult)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    create_all(conn)
    build_fixture(conn)

    findings = detect_fast_closure(conn)  # ground truth NOT passed in
    detected_case_ids = {f.case_id for f in findings}
    result = evaluate(conn, detected_case_ids, use_case_type="fast_closure")
    conn.close()
    return findings, result


def print_report(findings, result) -> None:
    print("=" * 78)
    print("FAST CLOSURE - DETECTOR FINDINGS (computed from observable data only)")
    print("=" * 78)
    if not findings:
        print("  (no findings)")
    for f in findings:
        print(f"  case_id={f.case_id}  entity_id={f.entity_id}")
        print(f"    observed_closure_minutes     = {f.observed_closure_minutes}")
        print(f"    peer_baseline_median_minutes = {f.peer_baseline_median_minutes}  (peer_group_size={f.peer_group_size})")
        print(f"    lower_fence_minutes          = {f.lower_fence_minutes}  (k={f.k})")
        print(f"    reason: {f.reason}")
        print()

    print("=" * 78)
    print("GROUND-TRUTH EVALUATION (ground truth read ONLY here, after detection)")
    print("=" * 78)
    print(f"  expected true anomalies  : {sorted(result.expected_anomaly_case_ids)}")
    print(f"  detected by detector     : {sorted(result.detected_case_ids)}")
    print(f"  correctly detected       : {sorted(result.correctly_detected)}")
    print(f"  missed                   : {sorted(result.missed)}")
    print(f"  unexpected detections    : {sorted(result.unexpected)}")
    print()
    print("=" * 78)
    print("FALSE-POSITIVE CONTROL CHECK")
    print("=" * 78)
    print(f"  false-positive control case(s) : {sorted(result.false_positive_control_case_ids)}")
    print(f"  flagged by detector             : {sorted(result.false_positive_controls_flagged)}")
    if result.false_positive_controls_flagged:
        print(
            "  -> Flagged, as expected: this Day 1B detector uses closure "
            "duration only. Distinguishing this control from CASE-P05 requires "
            "corroborating fields (disposition, investigation_note_length), "
            "which is planned as a Day 2 enhancement, not this experiment's job."
        )
    else:
        print("  -> NOT flagged (better than the minimum bar for this experiment).")


def main() -> None:
    print("Running experiment (run 1)...\n")
    findings_1, result_1 = run_once()
    print_report(findings_1, result_1)

    print("\nRunning experiment again, independently (run 2), to check reproducibility...\n")
    findings_2, _result_2 = run_once()

    def _comparable(findings):
        return sorted(
            (f.case_id, f.observed_closure_minutes, f.peer_baseline_median_minutes, f.lower_fence_minutes)
            for f in findings
        )

    repr_1, repr_2 = _comparable(findings_1), _comparable(findings_2)
    reproducible = repr_1 == repr_2
    print(f"Reproducible across two independent runs: {reproducible}")
    if not reproducible:
        print("  run 1:", repr_1)
        print("  run 2:", repr_2)

    # Persist one inspectable, on-disk copy.
    go_no_go_db_path = DEFAULT_DB_PATH.parent / "go_no_go.db"
    if go_no_go_db_path.exists():
        go_no_go_db_path.unlink()
    conn = sqlite3.connect(str(go_no_go_db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    create_all(conn)
    build_fixture(conn)
    conn.close()
    print(f"\nPersisted inspectable copy at: {go_no_go_db_path}")

    # ---- GO / NO-GO DECISION ----
    obvious_seeded_case = "CASE-P05"
    go = (
        obvious_seeded_case in result_1.correctly_detected
        and reproducible
        and len(result_1.missed) == 0
    )
    print("\n" + "=" * 78)
    print("GO / NO-GO DECISION:", "GO" if go else "NO-GO")
    print("=" * 78)
    sys.exit(0 if go else 1)


if __name__ == "__main__":
    main()
