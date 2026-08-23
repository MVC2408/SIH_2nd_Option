"""Detection logic — NOT YET IMPLEMENTED.

Planned for Day 2. Three detectors, one per use case:

- fast_closure: peer-relative statistical threshold on
  case_record.opened_at / closed_at, within severity tier.
- no_escalation: rule-based check on escalation.escalated for
  high/critical-severity cases.
- quiet_critical_asset: peer-relative statistical threshold on event counts
  per asset, within criticality_tier.

Hard constraint carried over from Day 1 design (see src/db/schema.py and
docs/ARCHITECTURE.md): detectors must read only from entity, asset, event,
case_record, and escalation. They must never read from ground_truth.
ground_truth is evaluation-only and is consumed exclusively by
src/validation, after detection has already run.
"""
