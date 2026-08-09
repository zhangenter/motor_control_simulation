from pathlib import Path


class ControllerSourceService:
    """UTF-8 persistence for editable custom-controller source code."""

    @staticmethod
    def load(path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8")

    @staticmethod
    def save(path: str | Path, source: str) -> Path:
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".py")
        target.write_text(source, encoding="utf-8")
        return target
