from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

from .units import RPM_PER_RAD_S


class LoopMode(str, Enum):
    CURRENT = "电流单环"
    SPEED = "速度单环"
    POSITION = "位置单环"
    CURRENT_SPEED = "电流-速度"
    CURRENT_POSITION = "电流-位置"
    SPEED_POSITION = "速度-位置"
    CASCADE = "电流-速度-位置"


class CommandType(str, Enum):
    STEP = "阶跃"
    RAMP = "斜坡"
    SINE = "正弦"
    TRAPEZOID = "梯形"
    S_CURVE = "S曲线"
    MANUAL = "手动给定"
    TRAJECTORY = "表格轨迹"


class ReferenceType(str, Enum):
    POSITION = "位置输入"
    SPEED = "速度输入"
    CURRENT = "电流输入"


POSITION_OUTER_MODES = frozenset(
    {
        LoopMode.POSITION,
        LoopMode.CURRENT_POSITION,
        LoopMode.SPEED_POSITION,
        LoopMode.CASCADE,
    }
)


def has_position_outer_loop(mode: LoopMode) -> bool:
    return mode in POSITION_OUTER_MODES


def allowed_reference_types(mode: LoopMode) -> tuple[ReferenceType, ...]:
    if has_position_outer_loop(mode):
        return (ReferenceType.POSITION, ReferenceType.SPEED)
    if mode in (LoopMode.SPEED, LoopMode.CURRENT_SPEED):
        return (ReferenceType.SPEED,)
    return (ReferenceType.CURRENT,)


def default_reference_type(mode: LoopMode) -> ReferenceType:
    return allowed_reference_types(mode)[0]


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

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["control"]["mode"] = self.control.mode.value
        data["command"]["kind"] = self.command.kind.value
        data["command"]["reference_type"] = self.command.reference_type.value
        return data

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        source_speed_unit = str(data.get("speed_unit", "rad/s")).strip().lower()
        motor = MotorConfig(**data.get("motor", {}))
        sim = SimulationConfig(**data.get("simulation", {}))
        disturbance_data = dict(data.get("disturbance", {}))
        disturbance = DisturbanceConfig(**disturbance_data)
        control_data = dict(data.get("control", {}))
        provided_control_sections = {
            key for key, value in control_data.items() if isinstance(value, dict)
        }
        control_data["mode"] = _enum_value(LoopMode, control_data.get("mode", LoopMode.CASCADE.value))
        for key, default in (
            ("current", ControlConfig().current),
            ("speed", ControlConfig().speed),
            ("position", ControlConfig().position),
        ):
            value = control_data.get(key)
            control_data[key] = PIDConfig(**value) if isinstance(value, dict) else default
        control = ControlConfig(**control_data)
        command_data = dict(data.get("command", {}))
        command_data["kind"] = _enum_value(CommandType, command_data.get("kind", CommandType.STEP.value))
        command_data["reference_type"] = _enum_value(
            ReferenceType,
            command_data.get("reference_type", default_reference_type(control.mode).value),
        )
        if command_data["reference_type"] not in allowed_reference_types(control.mode):
            command_data["reference_type"] = default_reference_type(control.mode)
        command = CommandConfig(**command_data)
        if source_speed_unit != "rpm":
            _convert_legacy_speed_units(
                control,
                command,
                disturbance,
                provided_control_sections,
                command_data,
                disturbance_data,
            )
        return cls(
            name=data.get("name", "未命名实验"),
            speed_unit="rpm",
            motor=motor,
            control=control,
            command=command,
            disturbance=disturbance,
            simulation=sim,
        )

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


E = TypeVar("E", bound=Enum)


def _enum_value(enum_type: Type[E], value: Any) -> E:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        return list(enum_type)[0]


def _convert_legacy_speed_units(
    control: ControlConfig,
    command: CommandConfig,
    disturbance: DisturbanceConfig,
    provided_control_sections: set[str],
    command_data: Dict[str, Any],
    disturbance_data: Dict[str, Any],
) -> None:
    """Migrate configurations saved before speed values were standardized on rpm."""
    if "speed" in provided_control_sections:
        for field_name in ("kp", "ki", "kd", "kff"):
            setattr(
                control.speed,
                field_name,
                getattr(control.speed, field_name) / RPM_PER_RAD_S,
            )
    if "position" in provided_control_sections:
        for field_name in ("kp", "ki", "kd", "kff"):
            setattr(
                control.position,
                field_name,
                getattr(control.position, field_name) * RPM_PER_RAD_S,
            )
        control.position.output_limit *= RPM_PER_RAD_S
        control.position.integral_limit *= RPM_PER_RAD_S
    if "stribeck_velocity" in disturbance_data:
        disturbance.stribeck_velocity *= RPM_PER_RAD_S

    if command.reference_type == ReferenceType.SPEED:
        for field_name in ("amplitude", "offset", "manual_value"):
            if field_name in command_data:
                setattr(command, field_name, getattr(command, field_name) * RPM_PER_RAD_S)
        if "trajectory_value" in command_data:
            command.trajectory_value = [value * RPM_PER_RAD_S for value in command.trajectory_value]
