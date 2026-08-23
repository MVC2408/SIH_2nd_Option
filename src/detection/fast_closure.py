"""Fast-closure detector.

Flags cases whose closure duration is anomalously short relative to a peer
baseline, using a transparent, Tukey-fence-style statistical threshold.

Peer group = other cases sharing the same entity.sector (peer-group key,
per the locked schema) and the same case_record.severity, EXCLUDING the
case's own entity (leave-one-out, so an anomalous case can never inflate
its own baseline).

Reads ONLY entity and case_record. Never reads ground_truth -- see
src/detection/__init__.py for why that separation is a hard project rule,
not a convention.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime

DETECTION_TYPE = "fast_closure"
DEFAULT_K = 1.5  # standard Tukey lower-fence multiplier


@dataclass(frozen=True)
class FastClosureFinding:
    case_id: str
    entity_id: str
    detection_type: str
    observed_closure_minutes: float
    peer_baseline_median_minutes: float
    peer_group_size: int
    lower_fence_minutes: float
    k: float
    reason: str


def _closure_minutes(opened_at: str, closed_at: str) -> float:
    delta = datetime.fromisoformat(closed_at) - datetime.fromisoformat(opened_at)
    return delta.total_seconds() / 60.0


def _quartiles(values: list[float]) -> tuple[float, float]:
    """Return (Q1, Q3). For fewer than 4 peers, statistics.quantiles is not
    meaningful, so fall back to (min, max) as a conservative, clearly-labeled
    stand-in rather than silently producing a misleading number -- this is a
    documented limitation of small peer groups (see project roadmap)."""
    if len(values) < 4:
        return min(values), max(values)
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="exclusive")
    return q1, q3


def detect_fast_closure(
    conn: sqlite3.Connection, k: float = DEFAULT_K
) -> list[FastClosureFinding]:
    """Detect anomalously fast case closures using observable data only.

    `conn` must already have a populated entity/case_record schema. No
    ground_truth table access happens anywhere in this function -- that is
    enforced by never issuing a query against it here, not by convention.
    """
    rows = conn.execute(
        """
        SELECT c.case_id, c.entity_id, e.sector, c.severity, c.opened_at, c.closed_at
        FROM case_record c
        JOIN entity e ON e.entity_id = c.entity_id
        WHERE c.status = 'closed' AND c.closed_at IS NOT NULL;
        """
    ).fetchall()

    cases = [
        {
            "case_id": case_id,
            "entity_id": entity_id,
            "sector": sector,
            "severity": severity,
            "closure_minutes": _closure_minutes(opened_at, closed_at),
        }
        for case_id, entity_id, sector, severity, opened_at, closed_at in rows
    ]

    findings: list[FastClosureFinding] = []
    for case in cases:
        peers = [
            c["closure_minutes"]
            for c in cases
            if c["sector"] == case["sector"]
            and c["severity"] == case["severity"]
            and c["entity_id"] != case["entity_id"]  # leave-one-out
        ]
        if len(peers) < 2:
            # Not enough peers to establish any baseline -- skip rather than guess.
            continue

        peer_median = statistics.median(peers)
        q1, q3 = _quartiles(peers)
        iqr = q3 - q1
        lower_fence = peer_median - k * iqr

        if case["closure_minutes"] < lower_fence:
            findings.append(
                FastClosureFinding(
                    case_id=case["case_id"],
                    entity_id=case["entity_id"],
                    detection_type=DETECTION_TYPE,
                    observed_closure_minutes=round(case["closure_minutes"], 2),
                    peer_baseline_median_minutes=round(peer_median, 2),
                    peer_group_size=len(peers),
                    lower_fence_minutes=round(lower_fence, 2),
                    k=k,
                    reason=(
                        f"Case {case['case_id']} at entity {case['entity_id']} closed in "
                        f"{case['closure_minutes']:.1f} minutes, versus a peer "
                        f"({case['sector']}/{case['severity']}, n={len(peers)}) median of "
                        f"{peer_median:.1f} minutes (lower fence = {lower_fence:.1f} min, k={k})."
                    ),
                )
            )
    return findings
