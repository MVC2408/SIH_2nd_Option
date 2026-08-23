"""Hand-built, fully deterministic tiny dataset for the Day 1B Go/No-Go
fast-closure experiment.

This is NOT the full synthetic generator (that's src/generation/, built
later at full scale — 15-20 entities). This is a small, fixed, literal
dataset whose only job is to prove the fast-closure detection approach
works before that investment. Every value below is a hard-coded literal —
no randomness anywhere, so reproducibility is guaranteed by construction
rather than by a seed.

Uses the LOCKED canonical schema exactly as-is: entity.sector as the
peer-group key, case_record.{severity, opened_at, closed_at} for closure
duration, and an isolated ground_truth table that this module populates but
that src/detection/fast_closure.py must never read.
"""

from __future__ import annotations

import sqlite3

# Single sector -> every case shares one peer group, keeping the experiment
# small enough to hand-verify.
SECTOR = "power"
SEVERITY = "critical"

# entity_id -> entity_name
ENTITIES: dict[str, str] = {
    "ENT-P01": "Power Utility Alpha",
    "ENT-P02": "Power Utility Bravo",
    "ENT-P03": "Power Utility Charlie",
    "ENT-P04": "Power Utility Delta",
    "ENT-P05": "Power Utility Echo",     # true anomaly lives here
    "ENT-P06": "Power Utility Foxtrot",  # false-positive control lives here
}

# (case_id, entity_id, opened_at, closed_at, disposition, investigation_note_length)
# Four "normal" peers close critical cases in roughly 44-52 hours.
CASES: list[tuple[str, str, str, str, str, int]] = [
    ("CASE-P01", "ENT-P01", "2026-01-01T00:00:00", "2026-01-02T22:00:00", "confirmed_incident", 320),
    ("CASE-P02", "ENT-P02", "2026-01-01T00:00:00", "2026-01-03T04:00:00", "confirmed_incident", 410),
    ("CASE-P03", "ENT-P03", "2026-01-01T00:00:00", "2026-01-02T20:00:00", "confirmed_incident", 295),
    ("CASE-P04", "ENT-P04", "2026-01-01T00:00:00", "2026-01-03T02:00:00", "confirmed_incident", 360),
    # TRUE ANOMALY: closed in 5 minutes with a near-empty note. Observable
    # and obvious from timestamps alone -- no ground truth needed to see it.
    ("CASE-P05", "ENT-P05", "2026-01-01T00:00:00", "2026-01-01T00:05:00", "closed_no_note", 12),
    # FALSE-POSITIVE CONTROL: also fast (20 minutes) -- would trip a naive
    # closure-time-only rule just like CASE-P05 -- but is a legitimately
    # fast, thoroughly documented dismissal of a known benign trigger, not
    # negligence. Only the disposition + note length distinguish it from a
    # true anomaly; the Day 1B detector deliberately does not look at those
    # fields yet (see docs/GO_NO_GO_RESULT.md for why that's expected).
    ("CASE-P06", "ENT-P06", "2026-01-01T00:00:00", "2026-01-01T00:20:00", "false_positive_dismissed", 480),
]

# Ground truth. Populated here for later evaluation, but NEVER read by
# src/detection/fast_closure.py -- only by src/validation/evaluation.py,
# after detection has already run.
# (ground_truth_id, entity_id, case_id, use_case_type, status, explanation)
GROUND_TRUTH: list[tuple[str, str, str, str, str, str]] = [
    ("GT-P01", "ENT-P01", "CASE-P01", "fast_closure", "normal",
     "Plausible closure time for a critical case; no anomaly seeded."),
    ("GT-P02", "ENT-P02", "CASE-P02", "fast_closure", "normal",
     "Plausible closure time for a critical case; no anomaly seeded."),
    ("GT-P03", "ENT-P03", "CASE-P03", "fast_closure", "normal",
     "Plausible closure time for a critical case; no anomaly seeded."),
    ("GT-P04", "ENT-P04", "CASE-P04", "fast_closure", "normal",
     "Plausible closure time for a critical case; no anomaly seeded."),
    ("GT-P05", "ENT-P05", "CASE-P05", "fast_closure", "true_anomaly",
     "Seeded: critical case closed in 5 minutes with a 12-character note -- "
     "far too fast for genuine investigation, no documented justification."),
    ("GT-P06", "ENT-P06", "CASE-P06", "fast_closure", "false_positive_control",
     "Seeded: also fast (20 minutes) and would trip a naive closure-time-only "
     "rule, but disposition is 'false_positive_dismissed' with a thorough "
     "480-character note -- a legitimately fast, well-documented dismissal "
     "of a known benign trigger, not negligence."),
]


def build(conn: sqlite3.Connection) -> None:
    """Insert the fixed Go/No-Go dataset into an already schema-initialized connection."""
    for entity_id, entity_name in ENTITIES.items():
        conn.execute(
            "INSERT INTO entity (entity_id, entity_name, sector) VALUES (?, ?, ?);",
            (entity_id, entity_name, SECTOR),
        )
    for case_id, entity_id, opened_at, closed_at, disposition, note_len in CASES:
        conn.execute(
            """INSERT INTO case_record
                   (case_id, entity_id, severity, opened_at, closed_at, status, disposition, investigation_note_length)
               VALUES (?, ?, ?, ?, ?, 'closed', ?, ?);""",
            (case_id, entity_id, SEVERITY, opened_at, closed_at, disposition, note_len),
        )
    for gt_id, entity_id, case_id, use_case_type, status, explanation in GROUND_TRUTH:
        conn.execute(
            """INSERT INTO ground_truth
                   (ground_truth_id, entity_id, case_id, use_case_type, status, explanation)
               VALUES (?, ?, ?, ?, ?, ?);""",
            (gt_id, entity_id, case_id, use_case_type, status, explanation),
        )
    conn.commit()
