"""Synthetic data generator (Day 1, hours 4-6).

Produces a full-scale synthetic dataset (default 18 entities across 3
sectors) with seeded true anomalies and false-positive controls for all
three Day 2 use cases (fast_closure, no_escalation, quiet_critical_asset),
plus realistic noise (missing fields, business-hours-clustered timestamps,
severity-correlated closure times).

Modules:
    model.py        constants and illustrative distribution parameters
    config.py       GeneratorConfig (entity count, seed, output dir)
    build.py        entities/assets/roles/events/cases/escalations + anomaly injection
    ground_truth.py assembles the separate ground_truth table (seeded status lives ONLY here)
    validate.py     data-quality checks; raises GenerationError, fails loudly
    writer.py       CSV output
    report.py       human-readable summary printer
    pipeline.py     orchestrates the above; used by scripts/generate_data.py

All randomness flows through a single seeded random.Random instance (see
pipeline.py) -- the same seed always produces the same dataset, including
which entities/cases/assets host anomalies vs false-positive controls.

This is illustrative synthetic research/demo data. No distribution or
parameter here is claimed to represent real-world SOC/CSE statistics.
"""
