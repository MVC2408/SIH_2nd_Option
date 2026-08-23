# SAT-SA — Day 1 Architecture Note

## Pipeline (target end state, not all built yet)

```
generator            (Day 1 hrs 4-6, then full-scale)
    |
    v
validation            (structural checks — src/validation/checks.py, built Day 1)
    |
    v
SQLite                (schema built Day 1 — src/db/schema.py)
    |
    v
detectors             (Day 2 — fast_closure, no_escalation, quiet_critical_asset)
    |
    v
[future] Streamlit UI (Day 3 — not started)
```

As of end of Day 1 hour ~1 (this commit), only the **SQLite schema** and
**structural validation** layers exist. The generator, detectors, and UI are
stubs or not yet present — see the docstrings in `src/generation/__init__.py`
and `src/detection/__init__.py`.

## Why SQLite

- Zero external dependency, zero setup — matches the "no cloud, no external
  services" constraint that the real PS 157 deployment target (fully
  air-gapped) will require anyway, so nothing here needs to change later for
  that reason.
- A single file (`db/sat_sa.db`) is trivial to regenerate, inspect (e.g. with
  the `sqlite3` CLI or DB Browser for SQLite), and hand to a judge.
- Real foreign-key constraints let us catch data-model mistakes immediately
  (see `test_foreign_keys_are_enforced` in `tests/test_schema.py`) instead of
  discovering them during Day 2 detector debugging.

## Why deterministic synthetic data (not yet built, but designed for)

- No real CSE SOC data is available or should be used — see the project's
  prior roadmap document, Section 5.
- A **fixed random seed** (`src.config.RANDOM_SEED = 42`) means the same
  dataset — including exactly which entities/cases are seeded true anomalies
  versus false-positive controls — regenerates identically every run. This
  matters for two practical reasons: (1) detector thresholds can be tuned
  against a stable target instead of a moving one, and (2) if asked to
  reproduce a result live in front of judges, the team can regenerate the
  exact same dataset from scratch, which is a small but real credibility
  signal.

## Data model summary

Six tables. `entity` and `asset` describe *who* and *what*; `event` and
`case_record` describe *what happened*; `escalation` describes *how it was
handled*; `ground_truth` is a separate, isolated table used only to grade
detector output after the fact — never read by detection logic.

| Table | Purpose | Peer-group / criticality key |
|---|---|---|
| `entity` | A Critical Sector Entity (CSE) | `sector` (peer-group key) |
| `asset` | A system/asset belonging to an entity | `criticality_tier` |
| `event` | A raw alert | — |
| `case_record` | An investigation/case (may follow from an event) | — |
| `escalation` | Whether/how a case was escalated | — |
| `ground_truth` | Evaluation-only labels, never a detector input | — |

Full column-level rationale lives as comments directly in
`src/db/schema.py` — kept there rather than duplicated here, so there is
exactly one place to update when the schema changes.

### Note: `case`, not `case`

The case table is named `case_record`, not `case`, because `CASE` is a
reserved SQL keyword in SQLite. Using it as a bare table name works in some
contexts but causes confusing errors in others (e.g. inside `CASE WHEN`
expressions); `case_record` avoids the whole class of problem.

### Note: the event <-> case_record relationship is intentionally one-directional at the FK level

An event can lead to a case, and a case is normally triggered by an event —
conceptually bidirectional. Enforcing both directions as foreign keys would
create a circular dependency between the two tables. Only
`event.case_id -> case_record.case_id` is FK-enforced;
`case_record.related_event_id` is a plain column, a logical (not
constraint-enforced) pointer back to the triggering event. See the
docstring at the top of `src/db/schema.py` for the same note in code.

## Peer groups

Detection (Day 2) compares an entity or asset against *comparable* others,
not the entire population — e.g. "this bank's case-closure speed vs. other
banks," not "vs. every CSE regardless of sector." `entity.sector` is the
peer-group key for entity-level comparisons (`fast_closure`,
`no_escalation`); `asset.criticality_tier` is the peer-group key for
asset-level comparisons (`quiet_critical_asset`), since a "critical" asset
should be compared to other "critical" assets, not to "low" tier ones.

## Ground truth design

Every ground-truth row has a `use_case_type` (which of the three detectors
it's relevant to) and a `status`, one of:

- `normal` — nothing seeded; a plain baseline record.
- `true_anomaly` — deliberately seeded to be caught by the corresponding
  detector.
- `false_positive_control` — deliberately constructed to *look* suspicious
  under a naive single-metric rule (e.g. a fast closure), but with a
  legitimate reason it should **not** be flagged (e.g. it was correctly and
  quickly dismissed as a known, well-documented false positive, with a full
  disposition note). This is not the same as an ordinary `normal` record —
  it exists specifically to test whether a detector is naive (single
  threshold) or genuinely discriminating (uses enough context to tell the
  two apart). Constructing at least one real false-positive control, not
  just labeling a normal record as one, is required by the project rules
  and is planned for the Day 1 hours 4-6 generator work.

`ground_truth` is intentionally its own table with no detector-input table
referencing it (`test_ground_truth_is_not_referenced_by_detector_input_tables`
in `tests/test_schema.py` checks this structurally). Detectors are written
against `entity` / `asset` / `event` / `case_record` / `escalation` only;
`ground_truth` is read exclusively by the (not-yet-built) evaluation step
that runs *after* detection, to compute precision/recall.
