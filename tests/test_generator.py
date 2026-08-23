"""Tests for the full synthetic data generator (Day 1C).

Uses a smaller entity count (15, the documented floor) for test speed where
count doesn't matter to the assertion, and the default (18) where realistic
scale matters.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.generation.config import GeneratorConfig
from src.generation.pipeline import generate_dataset
from src.generation.validate import GenerationError, validate_dataset


@pytest.fixture()
def small_dataset():
    config = GeneratorConfig(num_entities=15, seed=123, output_dir=None)  # type: ignore[arg-type]
    return generate_dataset(config)


# ---------------------------------------------------------------------------
# Entity count / structure
# ---------------------------------------------------------------------------

def test_entity_count_matches_request(small_dataset):
    assert len(small_dataset["entity"]) == 15


def test_entity_count_below_minimum_is_rejected():
    with pytest.raises(ValueError):
        GeneratorConfig(num_entities=5, seed=1, output_dir=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "table,key",
    [
        ("entity", "entity_id"),
        ("asset", "asset_id"),
        ("event", "event_id"),
        ("case_record", "case_id"),
        ("escalation", "escalation_id"),
        ("ground_truth", "ground_truth_id"),
    ],
)
def test_ids_are_unique(small_dataset, table, key):
    ids = [row[key] for row in small_dataset[table]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

def test_every_asset_references_a_real_entity(small_dataset):
    entity_ids = {e["entity_id"] for e in small_dataset["entity"]}
    for asset in small_dataset["asset"]:
        assert asset["entity_id"] in entity_ids


def test_every_case_references_a_real_entity(small_dataset):
    entity_ids = {e["entity_id"] for e in small_dataset["entity"]}
    for case in small_dataset["case_record"]:
        assert case["entity_id"] in entity_ids


def test_every_escalation_references_a_real_case(small_dataset):
    case_ids = {c["case_id"] for c in small_dataset["case_record"]}
    for esc in small_dataset["escalation"]:
        assert esc["case_id"] in case_ids


def test_every_ground_truth_row_references_real_records(small_dataset):
    entity_ids = {e["entity_id"] for e in small_dataset["entity"]}
    case_ids = {c["case_id"] for c in small_dataset["case_record"]}
    asset_ids = {a["asset_id"] for a in small_dataset["asset"]}
    for gt in small_dataset["ground_truth"]:
        assert gt["entity_id"] in entity_ids
        if gt["case_id"] is not None:
            assert gt["case_id"] in case_ids
        if gt["asset_id"] is not None:
            assert gt["asset_id"] in asset_ids


# ---------------------------------------------------------------------------
# Timestamps / closure logic
# ---------------------------------------------------------------------------

def test_closed_cases_have_closed_at_after_opened_at(small_dataset):
    for case in small_dataset["case_record"]:
        if case["status"] == "closed":
            opened = datetime.fromisoformat(case["opened_at"])
            closed = datetime.fromisoformat(case["closed_at"])
            assert closed > opened


def test_open_cases_have_no_closed_at(small_dataset):
    for case in small_dataset["case_record"]:
        if case["status"] == "open":
            assert case["closed_at"] is None


# ---------------------------------------------------------------------------
# Every entity has at least one critical asset (structural guarantee)
# ---------------------------------------------------------------------------

def test_every_entity_has_a_critical_asset(small_dataset):
    critical_by_entity = {
        a["entity_id"] for a in small_dataset["asset"] if a["criticality_tier"] == "critical"
    }
    entity_ids = {e["entity_id"] for e in small_dataset["entity"]}
    assert critical_by_entity == entity_ids


# ---------------------------------------------------------------------------
# Seeded anomalies / false-positive controls present
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("use_case", ["fast_closure", "no_escalation", "quiet_critical_asset"])
def test_true_anomaly_present_for_each_use_case(small_dataset, use_case):
    statuses = [gt["status"] for gt in small_dataset["ground_truth"] if gt["use_case_type"] == use_case]
    assert "true_anomaly" in statuses


@pytest.mark.parametrize("use_case", ["fast_closure", "no_escalation", "quiet_critical_asset"])
def test_false_positive_control_present_for_each_use_case(small_dataset, use_case):
    statuses = [gt["status"] for gt in small_dataset["ground_truth"] if gt["use_case_type"] == use_case]
    assert "false_positive_control" in statuses


def test_no_record_anywhere_has_an_is_anomaly_style_field(small_dataset):
    """Structural enforcement of the project rule: anomaly status must live
    ONLY in ground_truth, never as a flag on an operational record."""
    forbidden_keys = {"is_anomaly", "anomaly", "is_seeded", "seeded", "anomaly_flag"}
    for table_name, rows in small_dataset.items():
        if table_name == "ground_truth":
            continue
        for row in rows:
            assert forbidden_keys.isdisjoint(row.keys()), f"{table_name} row has a forbidden flag field: {row.keys() & forbidden_keys}"


# ---------------------------------------------------------------------------
# Determinism / reproducibility
# ---------------------------------------------------------------------------

def test_same_seed_produces_identical_dataset():
    config_a = GeneratorConfig(num_entities=15, seed=99, output_dir=None)  # type: ignore[arg-type]
    config_b = GeneratorConfig(num_entities=15, seed=99, output_dir=None)  # type: ignore[arg-type]
    dataset_a = generate_dataset(config_a)
    dataset_b = generate_dataset(config_b)
    assert dataset_a == dataset_b


def test_different_seed_produces_different_but_still_valid_dataset():
    config_a = GeneratorConfig(num_entities=15, seed=1, output_dir=None)  # type: ignore[arg-type]
    config_b = GeneratorConfig(num_entities=15, seed=2, output_dir=None)  # type: ignore[arg-type]
    dataset_a = generate_dataset(config_a)
    dataset_b = generate_dataset(config_b)
    assert dataset_a["case_record"] != dataset_b["case_record"]
    # generate_dataset() already raised GenerationError internally if either
    # was structurally invalid, so reaching this point is itself the proof;
    # re-validate explicitly too, for a clear, direct assertion.
    problems_a = validate_dataset(
        dataset_a["entity"], dataset_a["asset"], dataset_a["event"],
        dataset_a["case_record"], dataset_a["escalation"], dataset_a["ground_truth"],
    )
    problems_b = validate_dataset(
        dataset_b["entity"], dataset_b["asset"], dataset_b["event"],
        dataset_b["case_record"], dataset_b["escalation"], dataset_b["ground_truth"],
    )
    assert problems_a == []
    assert problems_b == []


# ---------------------------------------------------------------------------
# Validation catches injected corruption (proves the validator isn't a no-op)
# ---------------------------------------------------------------------------

def test_validator_rejects_dangling_foreign_key(small_dataset):
    corrupted_assets = list(small_dataset["asset"])
    corrupted_assets[0] = {**corrupted_assets[0], "entity_id": "ENT-DOES-NOT-EXIST"}
    problems = validate_dataset(
        small_dataset["entity"], corrupted_assets, small_dataset["event"],
        small_dataset["case_record"], small_dataset["escalation"], small_dataset["ground_truth"],
    )
    assert any("unknown entity_id" in p for p in problems)


def test_validator_rejects_missing_true_anomaly(small_dataset):
    filtered_gt = [
        gt for gt in small_dataset["ground_truth"]
        if not (gt["use_case_type"] == "fast_closure" and gt["status"] == "true_anomaly")
    ]
    problems = validate_dataset(
        small_dataset["entity"], small_dataset["asset"], small_dataset["event"],
        small_dataset["case_record"], small_dataset["escalation"], filtered_gt,
    )
    assert any("no true_anomaly ground truth present for use_case 'fast_closure'" in p for p in problems)
