from typing import Protocol


class CustomControllerRuntime(Protocol):
    """Runtime contract consumed by simulations and application services."""

    @property
    def running(self) -> bool: ...

    def start(self, code: str) -> None: ...

    def update(
        self,
        state: dict[str, float],
        reference: dict[str, float],
        dt: float,
    ) -> tuple[float, float]: ...

    def stop(self) -> None: ...
