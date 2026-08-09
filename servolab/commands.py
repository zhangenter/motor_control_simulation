from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from .config import CommandConfig, CommandType


def command_value(config: CommandConfig, time_s: float) -> float:
    """Evaluate the configured reference at ``time_s``."""
    t = time_s - config.start_time
    if config.kind == CommandType.MANUAL:
        return config.manual_value
    if config.kind == CommandType.TRAJECTORY:
        return trajectory_value(config, time_s)
    if t < 0.0:
        return config.offset
    if config.kind == CommandType.STEP:
        return config.offset + config.amplitude
    if config.kind == CommandType.RAMP:
        rise = max(config.rise_time, 1e-9)
        return config.offset + config.amplitude * min(t / rise, 1.0)
    if config.kind == CommandType.SINE:
        return config.offset + config.amplitude * math.sin(2.0 * math.pi * config.frequency * t)
    if config.kind == CommandType.S_CURVE:
        x = min(max(t / max(config.rise_time, 1e-9), 0.0), 1.0)
        blend = 10.0 * x**3 - 15.0 * x**4 + 6.0 * x**5
        return config.offset + config.amplitude * blend
    if config.kind == CommandType.TRAPEZOID:
        rise = max(config.rise_time, 1e-9)
        hold = max(config.hold_time, 0.0)
        period = max(4.0 * rise + 2.0 * hold, 1e-9)
        phase = t % period
        if phase < rise:
            unit = phase / rise
        elif phase < rise + hold:
            unit = 1.0
        elif phase < 3.0 * rise + hold:
            unit = 1.0 - (phase - rise - hold) / rise
        elif phase < 3.0 * rise + 2.0 * hold:
            unit = -1.0
        else:
            unit = -1.0 + (phase - 3.0 * rise - 2.0 * hold) / rise
        return config.offset + config.amplitude * unit
    return config.offset


def trajectory_value(config: CommandConfig, time_s: float) -> float:
    if not config.trajectory_time or not config.trajectory_value:
        return config.manual_value
    size = min(len(config.trajectory_time), len(config.trajectory_value))
    return float(
        np.interp(
            time_s,
            np.asarray(config.trajectory_time[:size], dtype=float),
            np.asarray(config.trajectory_value[:size], dtype=float),
        )
    )


def load_trajectory_csv(path: str | Path) -> tuple[list[float], list[float]]:
    """Load a two-column ``time,value`` trajectory CSV."""
    times: list[float] = []
    values: list[float] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row_index, row in enumerate(csv.reader(handle)):
            if len(row) < 2:
                continue
            try:
                time_value, setpoint = float(row[0]), float(row[1])
            except ValueError:
                if row_index == 0:
                    continue
                raise ValueError(f"轨迹 CSV 第 {row_index + 1} 行不是有效数值")
            if times and time_value <= times[-1]:
                raise ValueError("轨迹时间列必须严格递增")
            times.append(time_value)
            values.append(setpoint)
    if len(times) < 2:
        raise ValueError("轨迹 CSV 至少需要两个有效数据点")
    return times, values

