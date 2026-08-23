"""Write generated tables to CSV files -- a clean intermediate format ready
for straightforward SQLite ingestion later (Day 1, hours 6-8; not built by
this task). One file per table, column order taken from the first row's
keys so it matches the dict shape produced by src/generation/build.py and
ground_truth.py exactly.
"""

from __future__ import annotations

import csv
from pathlib import Path

TABLE_FILENAMES = {
    "entity": "entities.csv",
    "asset": "assets.csv",
    "event": "events.csv",
    "case_record": "cases.csv",
    "escalation": "escalations.csv",
    "ground_truth": "ground_truth.csv",
}


def write_table_csv(output_dir: Path, table_name: str, rows: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = TABLE_FILENAMES[table_name]
    path = output_dir / filename
    if not rows:
        path.write_text("")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_all(output_dir: Path, tables: dict[str, list[dict]]) -> dict[str, Path]:
    paths = {}
    for table_name, rows in tables.items():
        paths[table_name] = write_table_csv(output_dir, table_name, rows)
    return paths
