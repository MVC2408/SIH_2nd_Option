# SAT-SA — Supervisory Analytics Tool for SOC Assessment

SIH 2026, PS 157. An explainable, deterministic anomaly-detection MVP that
helps a supervisor (NCIIPC) identify which Critical Sector Entities (CSEs)
need closer manual review, by detecting **execution gaps** and **negative
space** in SOC alert/case-management metadata — not by monitoring live
traffic or replacing the SOC itself.

**All data in this project is synthetic.** No real CSE, SOC, or NCIIPC data
is used anywhere, at any stage. See `docs/ARCHITECTURE.md` for why.

## Current status: Day 1 — Foundation only

This repository currently contains **only the database schema and its
structural tests.** It does **not** yet contain:

- a synthetic data generator (planned: today, hours 4-6)
- any detection logic (planned: Day 2)
- a dashboard (planned: Day 3)

If you're looking for the actual anomaly detectors or a UI, they don't
exist yet — this commit is schema + tests only, by design (see the Day 1
plan in the project roadmap document).

## Project structure

```
sat-sa/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── config.py            # shared constants: paths, random seed, vocab
│   ├── db/
│   │   ├── schema.py        # canonical SQLite schema (DDL)
│   │   └── connection.py    # connection + init helpers
│   ├── generation/          # synthetic data generator — STUB, not built yet
│   ├── detection/           # detection logic — STUB, not built yet
│   └── validation/
│       └── checks.py        # structural schema-validation helpers
├── scripts/
│   └── init_db.py           # creates db/sat_sa.db from the schema
├── tests/
│   ├── conftest.py
│   └── test_schema.py
├── data/generated/          # synthetic data output lands here (not yet)
├── db/                      # db/sat_sa.db lands here (git-ignored)
└── docs/
    └── ARCHITECTURE.md
```

## Install

Requires Python 3.10+ (uses `list[str]`-style type hints and match-free
modern syntax; no 3.9-only issues, but not tested below 3.10).

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Run

Create the database (idempotent — safe to re-run):

```bash
python scripts/init_db.py
```

Expected output: a list of the six canonical tables, each marked `[OK]`.

Run the test suite:

```bash
pytest -v
```

## Why no data yet

Building the schema and proving it can represent all three Day-2 detection
use cases (`fast_closure`, `no_escalation`, `quiet_critical_asset`) *before*
generating data was a deliberate ordering choice, not an oversight — it
means the generator (built next) is writing against a schema already known
to support everything the detectors will need, rather than discovering a
schema gap mid-generation.

See `docs/ARCHITECTURE.md` for the full data model rationale, and the
project roadmap document for the Day 2-4 plan.
