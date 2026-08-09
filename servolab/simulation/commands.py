from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from ..config import CommandConfig, CommandType


def command_value(config: CommandConfig, time_s: float) -> float:
    elapsed = time_s - config.start_time
    if config.kind == CommandType.MANUAL:
        return config.manual_value
    if config.kind == CommandType.TRAJECTORY:
        return trajectory_value(config, time_s)
    if elapsed < 0.0:
        return config.offset
    if config.kind == CommandType.STEP:
        return config.offset + config.amplitude
    if config.kind == CommandType.RAMP:
        return config.offset + config.amplitude * elapsed / max(config.rise_time, 1e-9)
    if config.kind == CommandType.SINE:
        return config.offset + config.amplitude * math.sin(2.0 * math.pi * config.frequency * elapsed)
    if config.kind == CommandType.TRAPEZOID:
        rise = max(config.rise_time, 1e-9)
        if elapsed < rise:
            scale = elapsed / rise
        elif elapsed < rise + config.hold_time:
            scale = 1.0
        elif elapsed < 2.0 * rise + config.hold_time:
            scale = 1.0 - (elapsed - rise - config.hold_time) / rise
        else:
            scale = 0.0
        return config.offset + config.amplitude * scale
    if config.kind == CommandType.S_CURVE:
        rise = max(config.rise_time, 1e-9)
        if elapsed < rise:
            phase = min(max(elapsed / rise, 0.0), 1.0)
            scale = phase * phase * (3.0 - 2.0 * phase)
        elif elapsed < rise + config.hold_time:
            scale = 1.0
        elif elapsed < 2.0 * rise + config.hold_time:
            phase = min(max((elapsed - rise - config.hold_time) / rise, 0.0), 1.0)
            scale = 1.0 - phase * phase * (3.0 - 2.0 * phase)
        else:
            scale = 0.0
        return config.offset + config.amplitude * scale
    return config.offset


def trajectory_value(config: CommandConfig, time_s: float) -> float:
    if not config.trajectory_time or not config.trajectory_value:
        return config.offset
    return float(
        np.interp(
            time_s,
            np.asarray(config.trajectory_time, dtype=float),
            np.asarray(config.trajectory_value, dtype=float),
        )
    )


def load_trajectory_csv(path: str | Path) -> tuple[list[float], list[float]]:
    times: list[float] = []
    values: list[float] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row_index, row in enumerate(reader, start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            try:
                time_s, value = float(row[0]), float(row[1])
            except (ValueError, IndexError):
                if row_index == 1:
                    continue
                raise ValueError(f"轨迹 CSV 第 {row_index} 行不是 time,value 数值") from None
            if times and time_s <= times[-1]:
                raise ValueError("轨迹时间必须严格递增")
            times.append(time_s)
            values.append(value)
    if len(times) < 2:
        raise ValueError("轨迹 CSV 至少需要两个有效数据点")
    return times, values
