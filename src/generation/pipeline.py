"""Orchestrates the full generation pipeline: entities -> assets -> roles ->
events -> cases -> escalations -> anomaly injection -> ground truth ->
validation. Returns the in-memory tables; does not write to disk (that's
scripts/generate_data.py's job) and does not touch SQLite (Day 1, hours
6-8; not this task).
"""

from __future__ import annotations

import random

from src.generation import build, ground_truth as gt_module, validate
from src.generation.config import GeneratorConfig


def generate_dataset(config: GeneratorConfig) -> dict[str, list[dict]]:
    rng = random.Random(config.seed)

    entities = build.build_entities(rng, config.num_entities)
    assets = build.build_assets(rng, entities)
    roles = build.assign_roles(rng, entities, assets)

    events = build.build_events(rng, entities, assets, roles)
    cases = build.build_cases(rng, events)
    escalations = build.build_escalations(rng, cases)

    fast_closure_seeded = build.inject_fast_closure_anomalies(rng, cases, roles)
    no_escalation_seeded = build.inject_no_escalation_anomalies(rng, cases, escalations, roles)

    ground_truth = gt_module.build_ground_truth(
        entities=entities,
        assets=assets,
        cases=cases,
        events=events,
        fast_closure_seeded=fast_closure_seeded,
        no_escalation_seeded=no_escalation_seeded,
        quiet_critical_anomaly_assets=roles.quiet_critical_anomaly_assets,
        quiet_critical_fp_assets=roles.quiet_critical_fp_assets,
    )

    problems = validate.validate_dataset(entities, assets, events, cases, escalations, ground_truth)
    if problems:
        raise validate.GenerationError(problems)

    return {
        "entity": entities,
        "asset": assets,
        "event": events,
        "case_record": cases,
        "escalation": escalations,
        "ground_truth": ground_truth,
    }
