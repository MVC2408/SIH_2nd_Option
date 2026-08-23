# Synthetic Data Generator — Design Notes

## This is synthetic research/demo data

Every distribution and parameter in `src/generation/model.py` (event
volumes, severity weights, closure-time means, escalation probabilities)
is a hand-picked, illustrative value chosen to produce *plausible-looking*
synthetic data. **None of it is derived from, or claimed to represent, real
CSE/SOC operational statistics.** No real CSE, SOC, or NCIIPC data was used
anywhere in building this generator. See the project roadmap document,
Section 5, for why synthetic data is the only viable/appropriate approach
for PS 157 and how judge objections to that should be handled.

## Why generation is split into stages, not one big random dump

`entities -> assets -> roles -> events -> cases -> escalations -> anomaly
injection -> ground truth -> validation` (see `src/generation/pipeline.py`).
Roles (which entities/assets will host a seeded anomaly or false-positive
control) are decided *before* activity is generated, so:

- `quiet_critical_asset` anomalies/controls get their reduced event volume
  baked in structurally during event generation (not faked after the fact).
- `fast_closure` and `no_escalation` anomalies/controls are created by
  deliberately overwriting specific fields on an already-otherwise-normal
  case (closure timestamps, escalation flag), which is exactly what Day 1
  rule 10 permits ("the generator may deliberately manipulate source data
  to create anomalies") while rule 20 forbids adding a flag field for it.

## Where "ground truth" actually lives

`src/generation/ground_truth.py` is the *only* module that writes a
`true_anomaly` / `false_positive_control` / `normal` status anywhere. No
operational table (`entity`, `asset`, `event`, `case_record`, `escalation`)
ever gains a field recording that. This is checked structurally, not just by
convention — see `tests/test_generator.py::test_no_record_anywhere_has_an_is_anomaly_style_field`.

## Known, deliberately-not-hidden limitation: `quiet_critical_asset` false-positive control

The locked schema's `asset` table has no field for "why this asset is
legitimately quiet" (no notes/context/role column — only `asset_id`,
`entity_id`, `asset_name`, `criticality_tier`). The currently-specified
`quiet_critical_asset` detector (peer event-count comparison only, per the
project roadmap Section 11) therefore has **no way to structurally
distinguish** the seeded false-positive control from the seeded true
anomaly for this one use case — both will look identical to a
count-only detector. This is called out explicitly in the false-positive
control's own `ground_truth.explanation` text and is a genuine, currently
open limitation, not a hidden gap. (Contrast with `fast_closure` and
`no_escalation`, where `disposition`/`investigation_note_length` do give
a legitimate detector something to key off, and the false-positive control
is genuinely distinguishable given the right logic.)

If this needs to be closed later, the fix is a schema change (e.g. an
`asset.operational_role` or `asset.notes` field) — deliberately not made
here, since the schema is locked for this task.

## Reproducibility

All randomness flows through exactly one `random.Random(seed)` instance,
threaded explicitly through every generation function — nothing calls the
global `random` module. Same seed -> byte-identical CSV output, verified in
`tests/test_generator.py::test_same_seed_produces_identical_dataset` and, at
the file level, by running `scripts/generate_data.py` twice with the same
seed into different output directories and diffing them (see the Day 1C
report for the actual command and result).

## Scaling note

Every distribution parameter is keyed by category (sector, severity,
criticality tier), not by entity count, so `--entities` can be increased
well beyond 20 for later stress-testing without any code changes — only the
`MIN_ENTITIES` floor (12) and the recommended range (15–20, per the
roadmap) are enforced.
