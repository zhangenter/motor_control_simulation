from __future__ import annotations

from ..config import PIDConfig
from .types import PIDTerms


class PIDController:
    def __init__(self, config: PIDConfig):
        self.config = config
        self.integral = 0.0
        self.previous_error = 0.0
        self.filtered_measurement: float | None = None
        self.previous_measurement: float | None = None
        self.terms = PIDTerms()

    def reset(self) -> None:
        self.integral = 0.0
        self.previous_error = 0.0
        self.filtered_measurement = None
        self.previous_measurement = None
        self.terms = PIDTerms()

    def update(
        self,
        reference: float,
        measurement: float,
        dt: float,
        feedforward: float = 0.0,
    ) -> float:
        measured = self._filter_measurement(measurement)
        error = reference - measured
        p_term = self.config.kp * error
        d_term = self.config.kd * self._derivative(measured, dt)
        ff_term = self.config.kff * feedforward
        proposed_i = _clamp(
            self.integral + self.config.ki * error * dt,
            self.config.integral_limit,
        )
        raw = p_term + proposed_i + d_term + ff_term
        output = _clamp(raw, self.config.output_limit)
        if raw == output or error * raw <= 0.0:
            self.integral = proposed_i
        self.previous_error = error
        self.previous_measurement = measured
        self.terms = PIDTerms(p_term, self.integral, d_term, ff_term, output)
        return output

    def _filter_measurement(self, measurement: float) -> float:
        if not self.config.low_pass_enabled:
            return measurement
        alpha = min(max(self.config.low_pass_alpha, 0.001), 1.0)
        if self.filtered_measurement is None:
            self.filtered_measurement = measurement
        else:
            self.filtered_measurement += alpha * (measurement - self.filtered_measurement)
        return self.filtered_measurement

    def _derivative(self, measured: float, dt: float) -> float:
        if dt <= 0.0 or self.previous_measurement is None:
            return 0.0
        return -(measured - self.previous_measurement) / dt


def clamp(value: float, limit: float) -> float:
    return _clamp(value, limit)


def _clamp(value: float, limit: float) -> float:
    limit = abs(limit)
    return max(-limit, min(limit, value))
