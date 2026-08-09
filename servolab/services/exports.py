from pathlib import Path

from ..simulation import SimulationHistory


class ExportService:
    """Headless export use cases; presentation-specific image export stays outside."""

    @staticmethod
    def export_csv(history: SimulationHistory, path: str | Path) -> None:
        history.export_csv(path)
