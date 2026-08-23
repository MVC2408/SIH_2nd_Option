"""Ground-truth evaluation.

This is the ONLY module in the project allowed to read the ground_truth
table. It runs strictly AFTER detection, comparing already-produced
detector output (case IDs) against seeded ground truth. Detectors
(src/detection/*) never import or call anything from this module, and never
query ground_truth directly -- enforced structurally, see
tests/test_fast_closure_detector.py::test_detector_works_without_ground_truth_table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationResult:
    use_case_type: str
    expected_anomaly_case_ids: set[str]
    detected_case_ids: set[str]
    correctly_detected: set[str]
    missed: set[str]
    unexpected: set[str]
    false_positive_control_case_ids: set[str]
    false_positive_controls_flagged: set[str]


def evaluate(
    conn: sqlite3.Connection,
    detected_case_ids: set[str],
    use_case_type: str,
) -> EvaluationResult:
    """Compare detector output against seeded ground truth for one use case.

    `detected_case_ids` must already be computed by a detector using only
    observable data -- this function does not run any detection itself, it
    only grades output that was produced without seeing this table.
    """
    rows = conn.execute(
        "SELECT case_id, status FROM ground_truth WHERE use_case_type = ? AND case_id IS NOT NULL;",
        (use_case_type,),
    ).fetchall()

    expected = {case_id for case_id, status in rows if status == "true_anomaly"}
    fp_controls = {case_id for case_id, status in rows if status == "false_positive_control"}

    correctly_detected = expected & detected_case_ids
    missed = expected - detected_case_ids
    # "unexpected" = flagged cases ground truth doesn't explain as either a
    # true anomaly or a deliberate false-positive control (i.e. a plain
    # 'normal' case wrongly flagged) -- tracked separately from FP-control
    # flags, which are expected-to-be-tricky by design, not a plain miss.
    unexpected = detected_case_ids - expected - fp_controls
    fp_flagged = fp_controls & detected_case_ids

    return EvaluationResult(
        use_case_type=use_case_type,
        expected_anomaly_case_ids=expected,
        detected_case_ids=detected_case_ids,
        correctly_detected=correctly_detected,
        missed=missed,
        unexpected=unexpected,
        false_positive_control_case_ids=fp_controls,
        false_positive_controls_flagged=fp_flagged,
    )
