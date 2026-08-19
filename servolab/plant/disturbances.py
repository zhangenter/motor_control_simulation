from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..config import DisturbanceConfig, MotorConfig
from ..units import rad_s_to_rpm, rpm_to_rad_s


@dataclass(frozen=True)
class ElectricalDisturbance:
    bus_voltage: float
    applied_vd: float
    applied_vq: float
    pwm_vd: float = 0.0
    pwm_vq: float = 0.0
    dead_time_vd: float = 0.0
    dead_time_vq: float = 0.0
    back_emf_vd: float = 0.0
    back_emf_vq: float = 0.0


class DisturbanceModel:
    def __init__(self, config: DisturbanceConfig, motor: MotorConfig, dt: float, seed: int = 7):
        self.config = config
        self.motor = motor
        self.dt = dt
        self.rng = np.random.default_rng(seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def cogging(self, theta: float) -> float:
        cfg = self.config
        if not cfg.cogging_enabled:
            return 0.0
        phase = math.radians(cfg.cogging_phase_deg)
        order = max(cfg.cogging_harmonic, 1)
        return cfg.cogging_amplitude * (
            math.sin(order * theta + phase) + 0.25 * math.sin(2 * order * theta + 0.5 * phase)
        )

    def friction(self, speed_rpm: float, drive_torque: float) -> float:
        cfg = self.config
        if not cfg.friction_enabled:
            return 0.0
        zero_speed_threshold = rad_s_to_rpm(1e-4)
        if abs(speed_rpm) < zero_speed_threshold and abs(drive_torque) <= cfg.static_friction:
            return drive_torque
        direction_source = speed_rpm if abs(speed_rpm) >= zero_speed_threshold else drive_torque
        direction = 1.0 if direction_source >= 0.0 else -1.0
        speed = abs(speed_rpm)
        stribeck_speed = max(cfg.stribeck_velocity, 1e-6)
        dry = cfg.coulomb_friction + (cfg.static_friction - cfg.coulomb_friction) * math.exp(
            -(speed / stribeck_speed) ** 2
        )
        return direction * (dry + cfg.viscous_friction * rpm_to_rad_s(speed))

    def load(self, time_s: float) -> float:
        cfg = self.config
        if not cfg.load_enabled:
            return 0.0
        value = cfg.load_constant
        if time_s >= cfg.load_step_time:
            value += cfg.load_step
        value += cfg.load_sine_amplitude * math.sin(2.0 * math.pi * cfg.load_sine_frequency * time_s)
        if cfg.load_noise_std > 0.0:
            value += float(self.rng.normal(0.0, cfg.load_noise_std))
        return value

    def inertia(self, time_s: float) -> float:
        cfg = self.config
        if cfg.extra_inertia_enabled and time_s >= cfg.inertia_step_time:
            return max(cfg.extra_inertia, 0.0)
        return 0.0

    def electrical(
        self,
        time_s: float,
        theta: float,
        speed_rpm: float,
        id_current: float,
        iq_current: float,
        command_vd: float,
        command_vq: float,
    ) -> ElectricalDisturbance:
        bus_voltage = self._bus_voltage(time_s)
        nominal_bus = max(self.motor.dc_voltage, 1e-9)
        voltage_scale = bus_voltage / nominal_bus
        pwm_vd, pwm_vq = self._pwm_voltage(time_s, bus_voltage)
        dead_vd, dead_vq = self._dead_time_voltage(
            theta, id_current, iq_current, bus_voltage
        )
        applied_vd = command_vd * voltage_scale + pwm_vd + dead_vd
        applied_vq = command_vq * voltage_scale + pwm_vq + dead_vq
        applied_vd, applied_vq = _limit_vector(
            applied_vd,
            applied_vq,
            bus_voltage / math.sqrt(3.0),
        )
        emf_vd, emf_vq = self._back_emf_harmonic(theta, speed_rpm)
        return ElectricalDisturbance(
            bus_voltage,
            applied_vd,
            applied_vq,
            pwm_vd,
            pwm_vq,
            dead_vd,
            dead_vq,
            emf_vd,
            emf_vq,
        )

    def _bus_voltage(self, time_s: float) -> float:
        cfg = self.config
        nominal = max(self.motor.dc_voltage, 0.0)
        if not cfg.bus_voltage_enabled:
            return nominal
        offset = cfg.bus_voltage_offset_percent / 100.0
        ripple = cfg.bus_voltage_ripple_percent / 100.0
        frequency = max(cfg.bus_voltage_ripple_frequency, 0.0)
        scale = 1.0 + offset + ripple * math.sin(2.0 * math.pi * frequency * time_s)
        return max(nominal * scale, 0.0)

    def _pwm_voltage(self, time_s: float, bus_voltage: float) -> tuple[float, float]:
        cfg = self.config
        if not cfg.pwm_enabled or cfg.pwm_ripple_percent <= 0.0:
            return 0.0, 0.0
        requested_frequency = max(cfg.pwm_switching_frequency, 0.0)
        # The averaged dq model cannot resolve a carrier above Nyquist. Fold the
        # equivalent ripple into a deterministic, resolvable carrier instead.
        carrier_frequency = min(requested_frequency, 0.211 / max(self.dt, 1e-9))
        phase = 2.0 * math.pi * carrier_frequency * time_s
        amplitude = bus_voltage / math.sqrt(3.0) * cfg.pwm_ripple_percent / 100.0
        return amplitude * math.sin(phase), amplitude * math.sin(phase + 2.0 * math.pi / 3.0)

    def _dead_time_voltage(
        self,
        theta: float,
        id_current: float,
        iq_current: float,
        bus_voltage: float,
    ) -> tuple[float, float]:
        cfg = self.config
        if not cfg.dead_time_enabled or cfg.dead_time_us <= 0.0:
            return 0.0, 0.0
        electrical_theta = self.motor.pole_pairs * theta
        alpha = id_current * math.cos(electrical_theta) - iq_current * math.sin(electrical_theta)
        beta = id_current * math.sin(electrical_theta) + iq_current * math.cos(electrical_theta)
        phase_currents = (
            alpha,
            -0.5 * alpha + math.sqrt(3.0) * 0.5 * beta,
            -0.5 * alpha - math.sqrt(3.0) * 0.5 * beta,
        )
        fraction = cfg.dead_time_us * 1e-6 * max(cfg.pwm_switching_frequency, 0.0)
        phase_drop = min(bus_voltage * fraction, bus_voltage / math.sqrt(3.0) * 0.25)
        va, vb, vc = (-phase_drop * _sign(current) for current in phase_currents)
        error_alpha = 2.0 / 3.0 * (va - 0.5 * vb - 0.5 * vc)
        error_beta = 2.0 / 3.0 * (math.sqrt(3.0) * 0.5 * (vb - vc))
        vd = error_alpha * math.cos(electrical_theta) + error_beta * math.sin(electrical_theta)
        vq = -error_alpha * math.sin(electrical_theta) + error_beta * math.cos(electrical_theta)
        return vd, vq

    def _back_emf_harmonic(self, theta: float, speed_rpm: float) -> tuple[float, float]:
        cfg = self.config
        if not cfg.back_emf_enabled or cfg.back_emf_harmonic_percent <= 0.0:
            return 0.0, 0.0
        electrical_speed = self.motor.pole_pairs * rpm_to_rad_s(speed_rpm)
        base_emf = abs(electrical_speed * self.motor.flux)
        amplitude = base_emf * cfg.back_emf_harmonic_percent / 100.0
        angle = (
            max(cfg.back_emf_harmonic_order, 1) * self.motor.pole_pairs * theta
            + math.radians(cfg.back_emf_phase_deg)
        )
        return amplitude * math.sin(angle), amplitude * math.cos(angle)


def _limit_vector(d_axis: float, q_axis: float, limit: float) -> tuple[float, float]:
    magnitude = math.hypot(d_axis, q_axis)
    if magnitude <= max(limit, 0.0) or magnitude <= 0.0:
        return d_axis, q_axis
    scale = max(limit, 0.0) / magnitude
    return d_axis * scale, q_axis * scale


def _sign(value: float) -> float:
    if abs(value) < 1e-9:
        return 0.0
    return 1.0 if value > 0.0 else -1.0
