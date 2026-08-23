# SQLite Ingestion — Design Notes

## Clean-rebuild, not incremental upsert

`scripts/init_db.py` always deletes the existing database file before
recreating it and loading fresh from `data/generated/`. This was a
deliberate choice over incremental/upsert loading:

- The generator (Day 1C) is the single source of truth for the dataset; the
  database is a queryable *projection* of the generated CSVs, not an
  independent store that accumulates history across runs.
- Upsert logic (matching on primary key, deciding update-vs-insert) adds
  real complexity for a scenario that never actually arises in this
  project's workflow — the CSVs are always regenerated wholesale, never
  incrementally appended to.
- It structurally guarantees "no duplicate accumulation" (a stated Day 1D
  requirement) rather than relying on upsert logic being bug-free.

`src/db/ingest.py`'s `load_all` itself does plain `INSERT`, no
`INSERT OR REPLACE` / upsert — loading twice into an *already-populated*
database correctly raises `sqlite3.IntegrityError` on the duplicate primary
keys (see `tests/test_ingestion.py::test_loading_twice_into_the_same_db_without_rebuild_raises_integrity_error`).
That's intentional: it's the clean-rebuild step in `scripts/init_db.py`
that makes reruns safe, not silent deduplication inside the loader.

## No derived fields stored

`case_record` has no `closure_duration` column. Closure duration is always
computed at query time from `opened_at` / `closed_at`
(`julianday(closed_at) - julianday(opened_at)) * 24 * 60` in SQL, or
`datetime.fromisoformat` subtraction in Python — see
`src/detection/fast_closure.py` and
`src/validation/db_validation.py::verify_fast_closure_seeded`). This keeps
`opened_at`/`closed_at` as the single source of truth; there's no risk of
the stored duration silently drifting out of sync with the timestamps it
was computed from. Confirmed structurally by
`tests/test_ingestion.py::test_no_derived_closure_duration_column_exists`.

## Load order

Tables are loaded in FK-safe order: `entity, asset, case_record, event,
escalation, ground_truth` (`src/db/ingest.py::LOAD_ORDER`, matching
`src/db/schema.py::TABLE_NAMES`). `case_record` loads before `event`
because `event.case_id` is a foreign key to it; `escalation` and
`ground_truth` load last because they reference `case_record` (and, for
`ground_truth`, `entity`/`asset` too).

## Indexes: what and why (`src/db/indexes.py`)

Each index is tied to a specific Day 2 query pattern, not added
speculatively:

| Index | Serves |
|---|---|
| `entity(sector)` | peer-group grouping for `fast_closure`/`no_escalation` |
| `case_record(entity_id)` | join from case_record to entity |
| `case_record(severity, status)` | detector's `WHERE status='closed'` + severity-tier grouping |
| `asset(entity_id)` | join from asset to entity |
| `asset(criticality_tier)` | peer-group grouping for `quiet_critical_asset` (cross-entity, by tier) |
| `event(asset_id)` | per-asset event-count aggregation |
| `event(entity_id)` | per-entity event queries |
| `event(occurred_at)` | time-windowed queries |
| `ground_truth(use_case_type, status)` | evaluation queries ("all true_anomaly rows for X") |

`escalation.case_id` already has an implicit index from its `UNIQUE`
constraint in `schema.py` — no separate index was added for it.

## Validation is SQL-query-based, not a re-run of the generator's checks

`src/validation/db_validation.py::validate_database` re-derives every check
via direct SQL against the *loaded* database (dangling FK checks via
`LEFT JOIN ... WHERE x.id IS NULL`, closure-relationship checks via SQL
timestamp comparison, etc.) rather than trusting that whatever passed
generation-time validation (`src/generation/validate.py`) must still be
correct after a CSV round-trip. This caught nothing wrong in practice (the
CSV round-trip is lossless for this schema), but it's the right thing to
verify independently rather than assume.
