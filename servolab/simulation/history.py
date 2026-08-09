from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import numpy as np


CHANNELS = (
    "time",
    "command",
    "position_ref",
    "position",
    "position_actual",
    "position_error",
    "user_speed_ref",
    "speed_ref",
    "speed",
    "speed_actual",
    "speed_error",
    "current_ref",
    "id",
    "iq",
    "current_error",
    "torque",
    "load_torque",
    "friction_torque",
    "cogging_torque",
    "vd",
    "vq",
    "pid_p",
    "pid_i",
    "pid_d",
)


class SimulationHistory:
    def __init__(self) -> None:
        self.data: dict[str, list[float]] = {name: [] for name in CHANNELS}

    def clear(self) -> None:
        for values in self.data.values():
            values.clear()

    def append(self, sample: dict[str, float]) -> None:
        for channel in CHANNELS:
            self.data[channel].append(float(sample.get(channel, 0.0)))

    def arrays(self) -> dict[str, np.ndarray]:
        return {key: np.asarray(values, dtype=float) for key, values in self.data.items()}

    def snapshot(self) -> dict[str, list[float]]:
        return {key: list(values) for key, values in self.data.items()}

    def __len__(self) -> int:
        return len(self.data["time"])

    def export_csv(self, path: str | Path, channels: Iterable[str] = CHANNELS) -> None:
        selected = [name for name in channels if name in self.data]
        with Path(path).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(selected)
            writer.writerows(zip(*(self.data[name] for name in selected)))
