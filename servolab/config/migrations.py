from __future__ import annotations

from typing import Any

from ..units import RPM_PER_RAD_S
from .models import CommandConfig, ControlConfig, DisturbanceConfig
from .topology import ReferenceType


def convert_legacy_speed_units(
    control: ControlConfig,
    command: CommandConfig,
    disturbance: DisturbanceConfig,
    provided_control_sections: set[str],
    command_data: dict[str, Any],
    disturbance_data: dict[str, Any],
) -> None:
    """Migrate configurations saved before speed values were standardized on rpm."""
    if "speed" in provided_control_sections:
        _scale_pid_gains(control.speed, 1.0 / RPM_PER_RAD_S)
    if "position" in provided_control_sections:
        _scale_pid_gains(control.position, RPM_PER_RAD_S)
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


def _scale_pid_gains(pid, factor: float) -> None:
    for field_name in ("kp", "ki", "kd", "kff"):
        setattr(pid, field_name, getattr(pid, field_name) * factor)
