"""Generator configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import GENERATED_DATA_DIR, RANDOM_SEED
from src.generation import model


@dataclass(frozen=True)
class GeneratorConfig:
    num_entities: int = 18
    seed: int = RANDOM_SEED
    output_dir: Path = GENERATED_DATA_DIR

    def __post_init__(self):
        if self.num_entities < model.MIN_ENTITIES:
            raise ValueError(
                f"num_entities={self.num_entities} is below the minimum of "
                f"{model.MIN_ENTITIES} needed for meaningful peer groups "
                f"(recommended range: {model.RECOMMENDED_ENTITY_RANGE[0]}-{model.RECOMMENDED_ENTITY_RANGE[1]})."
            )
