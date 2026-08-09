from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..units import RPM_PER_RAD_S
from .topology import CommandType, LoopMode, ReferenceType


@dataclass
class MotorConfig:
    resistance: float = 0.6
    ld: float = 0.0015
    lq: float = 0.0015
    flux: float = 0.055
    pole_pairs: int = 4
    inertia: float = 0.0008
    viscous: float = 0.0001
    dc_voltage: float = 48.0
    current_limit: float = 15.0


@dataclass
class PIDConfig:
    kp: float
    ki: float
    kd: float = 0.0
    kff: float = 0.0
    output_limit: float = 10.0
    integral_limit: float = 10.0
    low_pass_enabled: bool = False
    low_pass_alpha: float = 0.2


@dataclass
class ControlConfig:
    mode: LoopMode = LoopMode.CASCADE
    current: PIDConfig = field(
        default_factory=lambda: PIDConfig(4.0, 800.0, output_limit=27.0, integral_limit=20.0)
    )
    speed: PIDConfig = field(
        default_factory=lambda: PIDConfig(
            0.08 / RPM_PER_RAD_S,
            1.8 / RPM_PER_RAD_S,
            0.0,
            output_limit=12.0,
            integral_limit=8.0,
        )
    )
    position: PIDConfig = field(
        default_factory=lambda: PIDConfig(
            12.0 * RPM_PER_RAD_S,
            0.6 * RPM_PER_RAD_S,
            0.08 * RPM_PER_RAD_S,
            output_limit=120.0 * RPM_PER_RAD_S,
            integral_limit=30.0 * RPM_PER_RAD_S,
        )
    )
    current_feedforward: bool = True
    speed_feedforward: bool = False
    position_feedforward: bool = False
    auto_tune_reserved: bool = True


@dataclass
class CommandConfig:
    reference_type: ReferenceType = ReferenceType.POSITION
    kind: CommandType = CommandType.STEP
    amplitude: float = 6.283185307
    offset: float = 0.0
    frequency: float = 0.5
    start_time: float = 0.2
    rise_time: float = 0.5
    hold_time: float = 1.0
    manual_value: float = 0.0
    trajectory_time: list[float] = field(default_factory=list)
    trajectory_value: list[float] = field(default_factory=list)


@dataclass
class DisturbanceConfig:
    cogging_enabled: bool = False
    cogging_amplitude: float = 0.02
    cogging_harmonic: int = 6
    cogging_phase_deg: float = 0.0
    friction_enabled: bool = False
    static_friction: float = 0.04
    coulomb_friction: float = 0.025
    viscous_friction: float = 0.0002
    stribeck_velocity: float = 0.5 * RPM_PER_RAD_S
    load_enabled: bool = False
    load_constant: float = 0.0
    load_step: float = 0.08
    load_step_time: float = 1.5
    load_sine_amplitude: float = 0.0
    load_sine_frequency: float = 1.0
    load_noise_std: float = 0.0
    encoder_noise_std: float = 0.0
    encoder_resolution: int = 65536
    encoder_delay: float = 0.0
    extra_inertia_enabled: bool = False
    extra_inertia: float = 0.0
    inertia_step_time: float = 1.0


@dataclass
class SimulationConfig:
    dt: float = 0.0002
    duration: float = 4.0
    plot_interval: float = 0.002
    realtime_factor: float = 1.0
    random_seed: int = 7


@dataclass
class ExperimentConfig:
    name: str = "未命名实验"
    motor: MotorConfig = field(default_factory=MotorConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    command: CommandConfig = field(default_factory=CommandConfig)
    disturbance: DisturbanceConfig = field(default_factory=DisturbanceConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    speed_unit: str = "rpm"

    def to_dict(self) -> dict[str, Any]:
        from .serialization import experiment_to_dict

        return experiment_to_dict(self)

    def save(self, path: str | Path) -> None:
        from .serialization import save_experiment

        save_experiment(self, path)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        from .serialization import experiment_from_dict

        return experiment_from_dict(data)

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        from .serialization import load_experiment

        return load_experiment(path)
