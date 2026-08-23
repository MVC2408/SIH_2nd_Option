"""Validation utilities.

Two distinct meanings of "validation" exist in this project, kept in
separate concerns:

1. Structural/schema validation (this module, `checks.py`) — sanity checks
   that the database matches the canonical data model. Used by tests and,
   later, by the generator/ingestion scripts as a post-load sanity check.

2. Detector accuracy validation (planned for Day 2, likely a separate
   `evaluation.py`) — comparing detector output against `ground_truth` to
   compute precision/recall. Not implemented yet; do not add it here.
"""
