from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import json
from pathlib import Path
from typing import Any, TypeVar

from .migrations import convert_legacy_speed_units
from .models import (
    CommandConfig,
    ControlConfig,
    DisturbanceConfig,
    ExperimentConfig,
    MotorConfig,
    PIDConfig,
    SimulationConfig,
)
from .topology import (
    CommandType,
    LoopMode,
    ReferenceType,
    allowed_reference_types,
    default_reference_type,
)


def experiment_to_dict(config: ExperimentConfig) -> dict[str, Any]:
    data = asdict(config)
    data["control"]["mode"] = config.control.mode.value
    data["command"]["kind"] = config.command.kind.value
    data["command"]["reference_type"] = config.command.reference_type.value
    return data


def save_experiment(config: ExperimentConfig, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(experiment_to_dict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def experiment_from_dict(data: dict[str, Any]) -> ExperimentConfig:
    source_speed_unit = str(data.get("speed_unit", "rad/s")).strip().lower()
    motor = MotorConfig(**data.get("motor", {}))
    simulation = SimulationConfig(**data.get("simulation", {}))
    disturbance_data = dict(data.get("disturbance", {}))
    disturbance = DisturbanceConfig(**disturbance_data)
    control_data = dict(data.get("control", {}))
    provided_sections = {key for key, value in control_data.items() if isinstance(value, dict)}
    control = _control_from_dict(control_data)
    command_data = dict(data.get("command", {}))
    command = _command_from_dict(command_data, control.mode)
    if source_speed_unit != "rpm":
        convert_legacy_speed_units(
            control,
            command,
            disturbance,
            provided_sections,
            command_data,
            disturbance_data,
        )
    return ExperimentConfig(
        name=data.get("name", "未命名实验"),
        speed_unit="rpm",
        motor=motor,
        control=control,
        command=command,
        disturbance=disturbance,
        simulation=simulation,
    )


def load_experiment(path: str | Path) -> ExperimentConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return experiment_from_dict(data)


def _control_from_dict(data: dict[str, Any]) -> ControlConfig:
    data["mode"] = _enum_value(LoopMode, data.get("mode", LoopMode.CASCADE.value))
    defaults = ControlConfig()
    for key in ("current", "speed", "position"):
        value = data.get(key)
        data[key] = PIDConfig(**value) if isinstance(value, dict) else getattr(defaults, key)
    return ControlConfig(**data)


def _command_from_dict(data: dict[str, Any], mode: LoopMode) -> CommandConfig:
    data["kind"] = _enum_value(CommandType, data.get("kind", CommandType.STEP.value))
    data["reference_type"] = _enum_value(
        ReferenceType,
        data.get("reference_type", default_reference_type(mode).value),
    )
    if data["reference_type"] not in allowed_reference_types(mode):
        data["reference_type"] = default_reference_type(mode)
    return CommandConfig(**data)


E = TypeVar("E", bound=Enum)


def _enum_value(enum_type: type[E], value: Any) -> E:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        return list(enum_type)[0]
