"""Generate the full synthetic SAT-SA dataset and write it to CSV.

This is Day 1, hours 4-6 of the roadmap: produces entities/assets/events/
cases/escalations/ground_truth as CSV files, ready for SQLite ingestion
later (not this script's job -- see scripts/init_db.py for schema creation
and the not-yet-built ingestion step for loading these CSVs).

Usage:
    python scripts/generate_data.py
    python scripts/generate_data.py --entities 18 --seed 42
    python scripts/generate_data.py --entities 15 --seed 7 --output-dir data/generated/seed7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import GENERATED_DATA_DIR, RANDOM_SEED
from src.generation.config import GeneratorConfig
from src.generation.pipeline import generate_dataset
from src.generation.report import print_summary
from src.generation.validate import GenerationError
from src.generation.writer import write_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entities", type=int, default=18, help="Number of entities to generate (recommended: 15-20). Default: 18.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help=f"Random seed for reproducibility. Default: {RANDOM_SEED}.")
    parser.add_argument("--output-dir", type=Path, default=GENERATED_DATA_DIR, help=f"Output directory for CSV files. Default: {GENERATED_DATA_DIR}.")
    args = parser.parse_args()

    try:
        config = GeneratorConfig(num_entities=args.entities, seed=args.seed, output_dir=args.output_dir)
        tables = generate_dataset(config)
    except GenerationError as exc:
        print("GENERATION FAILED -- data quality validation found problems:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"GENERATION FAILED -- invalid configuration: {exc}", file=sys.stderr)
        sys.exit(1)

    paths = write_all(config.output_dir, tables)

    print_summary(
        entities=tables["entity"],
        assets=tables["asset"],
        events=tables["event"],
        cases=tables["case_record"],
        escalations=tables["escalation"],
        ground_truth=tables["ground_truth"],
    )

    print(f"\nseed = {config.seed}, entities requested = {config.num_entities}")
    print("Written files:")
    for table_name, path in paths.items():
        print(f"  {table_name:<14} -> {path}")


if __name__ == "__main__":
    main()
