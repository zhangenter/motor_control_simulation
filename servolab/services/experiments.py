from pathlib import Path

from ..config import ExperimentConfig
from ..simulation import load_trajectory_csv


class ExperimentService:
    """Headless experiment and trajectory persistence use cases."""

    @staticmethod
    def load(path: str | Path) -> ExperimentConfig:
        return ExperimentConfig.load(path)

    @staticmethod
    def save(config: ExperimentConfig, path: str | Path) -> None:
        config.save(path)

    @staticmethod
    def load_trajectory(path: str | Path) -> tuple[list[float], list[float]]:
        return load_trajectory_csv(path)
