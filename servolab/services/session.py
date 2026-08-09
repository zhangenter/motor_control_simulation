from __future__ import annotations

from ..config import ExperimentConfig
from ..control import CustomControllerProcess, CustomControllerRuntime
from ..simulation import ServoSimulation, SimulationHistory


class SimulationSession:
    """UI-independent lifecycle for an experiment and its optional controller runtime."""

    def __init__(
        self,
        config: ExperimentConfig | None = None,
        custom_controller: CustomControllerRuntime | None = None,
    ):
        self.config = config or ExperimentConfig()
        self.custom_controller = custom_controller or CustomControllerProcess(timeout_s=0.04)
        self.simulation = ServoSimulation(self.config)
        self.simulation.custom_controller = self.custom_controller
        self.running = False
        self.overlays: list[tuple[str, dict[str, list[float]]]] = []

    def apply_config(self, config: ExperimentConfig) -> None:
        self.running = False
        self.config = config
        self.simulation.apply_config(config)
        self.simulation.custom_controller = self.custom_controller

    def start(self) -> None:
        if self.simulation.time >= self.config.simulation.duration:
            self.simulation.reset()
        self.running = True

    def pause(self) -> None:
        self.running = False

    def reset(self) -> None:
        self.running = False
        self.simulation.reset()

    def step(self, steps: int = 1) -> dict[str, float]:
        return self.simulation.step(steps)

    def run_offline(self, duration=None, progress=None) -> SimulationHistory:
        self.running = False
        return self.simulation.run_offline(duration=duration, progress=progress)

    def keep_comparison(self) -> str | None:
        if len(self.simulation.history) < 2:
            return None
        if len(self.overlays) >= 4:
            self.overlays.pop(0)
        name = f"{self.config.name} #{len(self.overlays) + 1}"
        self.overlays.append((name, self.simulation.history.snapshot()))
        return name

    def clear_comparisons(self) -> None:
        self.overlays.clear()

    def start_custom_controller(self, source: str) -> None:
        self.custom_controller.start(source)
        self.set_custom_controller_enabled(True)

    def stop_custom_controller(self) -> None:
        self.set_custom_controller_enabled(False)
        self.custom_controller.stop()

    def set_custom_controller_enabled(self, enabled: bool) -> None:
        self.simulation.use_custom_controller = enabled and self.custom_controller.running

    def close(self) -> None:
        self.custom_controller.stop()
