from __future__ import annotations

import math
from dataclasses import dataclass

from ..units import RPM_PER_RAD_S


@dataclass(frozen=True)
class PIDTuningResult:
    """PID gains produced by a model-based loop tuning rule."""

    kp: float
    ki: float
    kd: float = 0.0


def tune_current_loop(
    resistance: float,
    inductance: float,
    bandwidth_hz: float,
) -> PIDTuningResult:
    """Tune an RL current plant by cancelling its electrical pole."""

    _require_positive("定子电阻", resistance)
    _require_positive("q 轴电感", inductance)
    omega_c = _angular_frequency(bandwidth_hz)
    return PIDTuningResult(
        kp=inductance * omega_c,
        ki=resistance * omega_c,
    )


def tune_speed_loop(
    inertia: float,
    viscous: float,
    pole_pairs: int,
    flux: float,
    natural_frequency_hz: float,
    damping_ratio: float,
) -> PIDTuningResult:
    """Tune a current-to-speed PI loop with speed represented in rpm."""

    _require_positive("转动惯量", inertia)
    _require_nonnegative("黏性系数", viscous)
    _require_positive("极对数", pole_pairs)
    _require_positive("永磁磁链", flux)
    _require_positive("阻尼比", damping_ratio)
    omega_n = _angular_frequency(natural_frequency_hz)
    torque_constant = 1.5 * pole_pairs * flux
    plant_gain = torque_constant * RPM_PER_RAD_S
    kp = (2.0 * damping_ratio * omega_n * inertia - viscous) / plant_gain
    if kp <= 0.0:
        raise ValueError("目标频率过低，无法得到正的速度环 Kp。")
    return PIDTuningResult(
        kp=kp,
        ki=omega_n * omega_n * inertia / plant_gain,
    )


def tune_position_loop(bandwidth_hz: float) -> PIDTuningResult:
    """Tune a position-to-speed outer loop using the standard P rule."""

    omega_c = _angular_frequency(bandwidth_hz)
    return PIDTuningResult(kp=omega_c * RPM_PER_RAD_S, ki=0.0, kd=0.0)


def _angular_frequency(frequency_hz: float) -> float:
    _require_positive("目标频率", frequency_hz)
    return 2.0 * math.pi * frequency_hz


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0:
        raise ValueError(f"{name}必须大于 0。")


def _require_nonnegative(name: str, value: float) -> None:
    if value < 0.0:
        raise ValueError(f"{name}不能小于 0。")
