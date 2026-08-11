from __future__ import annotations

from collections import deque
import math

import numpy as np

from .config import EncoderConfig, SpeedEstimatorConfig, SpeedEstimatorMethod
from .units import rad_s_to_rpm, rpm_to_rad_s


class EncoderModel:
    """Quantized, noisy, and delayed encoder position measurement."""

    def __init__(self, config: EncoderConfig, dt: float, seed: int = 7):
        self.config = config
        self.dt = dt
        self.rng = np.random.default_rng(seed)
        self.delay_queue: deque[float] = deque()

    def reset(self, seed: int | None = None) -> None:
        self.delay_queue.clear()
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def measure(self, theta: float) -> float:
        measured_theta = theta
        if self.config.resolution > 0:
            quantum = 2.0 * math.pi / self.config.resolution
            measured_theta = round(measured_theta / quantum) * quantum
        if self.config.noise_std > 0.0:
            measured_theta += float(self.rng.normal(0.0, self.config.noise_std))

        self.delay_queue.append(measured_theta)
        delay_steps = max(int(round(self.config.delay / max(self.dt, 1e-9))), 0)
        while len(self.delay_queue) > delay_steps + 1:
            self.delay_queue.popleft()
        return self.delay_queue[0]


class SpeedEstimator:
    """Estimate speed from encoder position, with an ideal comparison mode."""

    def __init__(self, config: SpeedEstimatorConfig, encoder: EncoderConfig | None = None):
        self.config = config
        self.encoder = encoder or EncoderConfig()
        self._active_method = config.method
        self.previous_position: float | None = None
        self.filtered_speed = 0.0
        self.position_estimate: float | None = None
        self.speed_estimate_rad_s = 0.0
        self.p00 = 0.0
        self.p01 = 0.0
        self.p10 = 0.0
        self.p11 = 0.0

    def reset(self) -> None:
        self._active_method = self.config.method
        self.previous_position = None
        self.filtered_speed = 0.0
        self.position_estimate = None
        self.speed_estimate_rad_s = 0.0
        self.p00 = self.p01 = self.p10 = self.p11 = 0.0

    def update(self, measured_position: float, dt: float, true_speed: float = 0.0) -> float:
        if self.config.method != self._active_method:
            self.reset()
        if self.config.method == SpeedEstimatorMethod.IDEAL:
            return true_speed
        if self.config.method == SpeedEstimatorMethod.PLL:
            return self._pll(measured_position, dt)
        if self.config.method == SpeedEstimatorMethod.ORTHOGONAL_PLL:
            return self._orthogonal_anti_windup_pll(measured_position, dt)
        if self.config.method == SpeedEstimatorMethod.KALMAN:
            return self._kalman(measured_position, dt)
        if self.config.method == SpeedEstimatorMethod.STATE_OBSERVER:
            return self._state_observer(measured_position, dt)

        raw_speed = self._position_difference(measured_position, dt)
        if self.config.method == SpeedEstimatorMethod.DIFFERENCE:
            return raw_speed

        cutoff = max(self.config.cutoff_frequency, 0.0)
        alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff * max(dt, 0.0))
        self.filtered_speed += alpha * (raw_speed - self.filtered_speed)
        return self.filtered_speed

    def _position_difference(self, measured_position: float, dt: float) -> float:
        if self.previous_position is None or dt <= 0.0:
            self.previous_position = measured_position
            return 0.0
        delta = measured_position - self.previous_position
        self.previous_position = measured_position
        return rad_s_to_rpm(delta / dt)

    def _pll(self, measured_position: float, dt: float) -> float:
        if not self._initialize_state(measured_position) or dt <= 0.0:
            return rad_s_to_rpm(self.speed_estimate_rad_s)
        proportional, integral = self._tracking_gains(
            self.config.pll_bandwidth,
            self.config.pll_damping,
            dt,
        )
        phase_error = _wrap_angle(measured_position - self.position_estimate)
        self.speed_estimate_rad_s += integral * phase_error * dt
        self.position_estimate += (
            self.speed_estimate_rad_s + proportional * phase_error
        ) * dt
        return rad_s_to_rpm(self.speed_estimate_rad_s)

    def _orthogonal_anti_windup_pll(self, measured_position: float, dt: float) -> float:
        """Track encoder phase with a bounded quadrature detector and PI anti-windup."""
        if not self._initialize_state(measured_position) or dt <= 0.0:
            return rad_s_to_rpm(self.speed_estimate_rad_s)

        proportional, integral = self._tracking_gains(
            self.config.pll_bandwidth,
            self.config.pll_damping,
            dt,
        )
        measured_sin = math.sin(measured_position)
        measured_cos = math.cos(measured_position)
        estimated_sin = math.sin(self.position_estimate)
        estimated_cos = math.cos(self.position_estimate)
        phase_error = measured_sin * estimated_cos - measured_cos * estimated_sin

        unlimited_speed = self.speed_estimate_rad_s + proportional * phase_error
        limited_speed = self._limit_pll_speed(unlimited_speed)
        anti_windup_gain = integral / proportional if proportional > 1e-12 else 0.0
        self.speed_estimate_rad_s += (
            integral * phase_error
            + anti_windup_gain * (limited_speed - unlimited_speed)
        ) * dt

        unlimited_speed = self.speed_estimate_rad_s + proportional * phase_error
        limited_speed = self._limit_pll_speed(unlimited_speed)
        self.position_estimate += limited_speed * dt
        return rad_s_to_rpm(limited_speed)

    def _limit_pll_speed(self, speed_rad_s: float) -> float:
        limit_rpm = max(self.config.pll_speed_limit, 0.0)
        if limit_rpm <= 0.0:
            return speed_rad_s
        limit_rad_s = rpm_to_rad_s(limit_rpm)
        return max(-limit_rad_s, min(limit_rad_s, speed_rad_s))

    def _kalman(self, measured_position: float, dt: float) -> float:
        if not self._initialize_kalman(measured_position) or dt <= 0.0:
            return rad_s_to_rpm(self.speed_estimate_rad_s)
        acceleration_variance = max(self.config.kalman_acceleration_noise, 1e-9) ** 2
        dt2, dt3, dt4 = dt * dt, dt**3, dt**4
        predicted_position = self.position_estimate + self.speed_estimate_rad_s * dt
        p00 = self.p00 + dt * (self.p01 + self.p10) + dt2 * self.p11
        p01 = self.p01 + dt * self.p11
        p10 = self.p10 + dt * self.p11
        p11 = self.p11
        p00 += 0.25 * acceleration_variance * dt4
        p01 += 0.5 * acceleration_variance * dt3
        p10 += 0.5 * acceleration_variance * dt3
        p11 += acceleration_variance * dt2

        innovation_variance = p00 + self._measurement_variance()
        position_gain = p00 / innovation_variance
        speed_gain = p10 / innovation_variance
        innovation = measured_position - predicted_position
        self.position_estimate = predicted_position + position_gain * innovation
        self.speed_estimate_rad_s += speed_gain * innovation
        self.p00 = (1.0 - position_gain) * p00
        self.p01 = (1.0 - position_gain) * p01
        self.p10 = p10 - speed_gain * p00
        self.p11 = p11 - speed_gain * p01
        return rad_s_to_rpm(self.speed_estimate_rad_s)

    def _state_observer(self, measured_position: float, dt: float) -> float:
        if not self._initialize_state(measured_position) or dt <= 0.0:
            return rad_s_to_rpm(self.speed_estimate_rad_s)
        position_gain, speed_gain = self._tracking_gains(
            self.config.observer_bandwidth,
            self.config.observer_damping,
            dt,
        )
        position_error = measured_position - self.position_estimate
        self.speed_estimate_rad_s += speed_gain * position_error * dt
        self.position_estimate += (
            self.speed_estimate_rad_s + position_gain * position_error
        ) * dt
        return rad_s_to_rpm(self.speed_estimate_rad_s)

    def _initialize_state(self, measured_position: float) -> bool:
        if self.position_estimate is not None:
            return True
        self.position_estimate = measured_position
        self.speed_estimate_rad_s = 0.0
        return False

    def _initialize_kalman(self, measured_position: float) -> bool:
        if self.position_estimate is not None:
            return True
        self._initialize_state(measured_position)
        self.p00 = self._measurement_variance()
        self.p11 = (2.0 * math.pi * 1000.0 / 60.0) ** 2
        return False

    def _measurement_variance(self) -> float:
        variance = max(self.encoder.noise_std, 0.0) ** 2
        if self.encoder.resolution > 0:
            quantum = 2.0 * math.pi / self.encoder.resolution
            variance += quantum * quantum / 12.0
        return max(variance, 1e-18)

    @staticmethod
    def _tracking_gains(bandwidth: float, damping: float, dt: float) -> tuple[float, float]:
        stable_bandwidth = min(max(bandwidth, 0.0), 0.1 / max(dt, 1e-9))
        natural_frequency = 2.0 * math.pi * stable_bandwidth
        damping = min(max(damping, 0.1), 5.0)
        return 2.0 * damping * natural_frequency, natural_frequency * natural_frequency


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi
