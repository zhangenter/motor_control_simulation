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
    EncoderConfig,
    ExperimentConfig,
    FeedbackConfig,
    MotorConfig,
    PIDConfig,
    SimulationConfig,
    SpeedEstimatorConfig,
    SpeedEstimatorMethod,
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
    data["feedback"]["speed_estimator"]["method"] = config.feedback.speed_estimator.method.value
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
    feedback = _feedback_from_dict(data.get("feedback"), disturbance_data)
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
        feedback=feedback,
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


def _feedback_from_dict(value: Any, disturbance_data: dict[str, Any]) -> FeedbackConfig:
    legacy_encoder = {
        "noise_std": disturbance_data.pop("encoder_noise_std", 0.0),
        "resolution": disturbance_data.pop("encoder_resolution", 65536),
        "delay": disturbance_data.pop("encoder_delay", 0.0),
    }
    if not isinstance(value, dict):
        return FeedbackConfig(
            encoder=EncoderConfig(**legacy_encoder),
            speed_estimator=SpeedEstimatorConfig(method=SpeedEstimatorMethod.IDEAL),
        )
    feedback_data = dict(value)
    encoder_value = feedback_data.pop("encoder", {})
    encoder_data = dict(legacy_encoder)
    if isinstance(encoder_value, dict):
        encoder_data.update(encoder_value)
    estimator_value = feedback_data.pop("speed_estimator", {})
    estimator_data = dict(estimator_value) if isinstance(estimator_value, dict) else {}
    legacy_methods = {
        "理想速度（绕过估算）": SpeedEstimatorMethod.IDEAL,
        "编码器位置差分": SpeedEstimatorMethod.DIFFERENCE,
        "位置差分 + 一阶低通": SpeedEstimatorMethod.FILTERED_DIFFERENCE,
    }
    method_value = estimator_data.get(
        "method",
        SpeedEstimatorMethod.FILTERED_DIFFERENCE.value,
    )
    estimator_data["method"] = legacy_methods.get(method_value) or _enum_value(
        SpeedEstimatorMethod,
        method_value,
    )
    return FeedbackConfig(
        encoder=EncoderConfig(**encoder_data),
        speed_estimator=SpeedEstimatorConfig(**estimator_data),
        **feedback_data,
    )


E = TypeVar("E", bound=Enum)


def _enum_value(enum_type: type[E], value: Any) -> E:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        return list(enum_type)[0]
