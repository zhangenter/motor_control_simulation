from __future__ import annotations

from collections import deque
import math

import numpy as np

from .config import DisturbanceConfig, MotorConfig
from .units import rad_s_to_rpm, rpm_to_rad_s


class DisturbanceModel:
    def __init__(self, config: DisturbanceConfig, motor: MotorConfig, dt: float, seed: int = 7):
        self.config = config
        self.motor = motor
        self.dt = dt
        self.rng = np.random.default_rng(seed)
        self.delay_queue: deque[tuple[float, float]] = deque()

    def reset(self, seed: int | None = None) -> None:
        self.delay_queue.clear()
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def cogging(self, theta: float) -> float:
        cfg = self.config
        if not cfg.cogging_enabled:
            return 0.0
        phase = math.radians(cfg.cogging_phase_deg)
        order = max(cfg.cogging_harmonic, 1)
        # Two harmonics make the teaching signal visibly non-ideal.
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

    def encoder(self, theta: float, speed_rpm: float) -> tuple[float, float]:
        cfg = self.config
        measured_theta = theta
        if cfg.encoder_resolution > 0:
            quantum = 2.0 * math.pi / cfg.encoder_resolution
            measured_theta = round(measured_theta / quantum) * quantum
        if cfg.encoder_noise_std > 0.0:
            measured_theta += float(self.rng.normal(0.0, cfg.encoder_noise_std))

        self.delay_queue.append((measured_theta, speed_rpm))
        delay_steps = max(int(round(cfg.encoder_delay / max(self.dt, 1e-9))), 0)
        while len(self.delay_queue) > delay_steps + 1:
            self.delay_queue.popleft()
        return self.delay_queue[0]
