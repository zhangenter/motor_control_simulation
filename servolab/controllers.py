from __future__ import annotations

from dataclasses import dataclass
import math

from .config import ControlConfig, LoopMode, MotorConfig, PIDConfig


@dataclass
class PIDTerms:
    p: float = 0.0
    i: float = 0.0
    d: float = 0.0
    ff: float = 0.0
    output: float = 0.0


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

    def update(self, reference: float, measurement: float, dt: float, feedforward: float = 0.0) -> float:
        cfg = self.config
        measured = measurement
        if cfg.low_pass_enabled:
            alpha = min(max(cfg.low_pass_alpha, 0.001), 1.0)
            if self.filtered_measurement is None:
                self.filtered_measurement = measured
            else:
                self.filtered_measurement += alpha * (measured - self.filtered_measurement)
            measured = self.filtered_measurement

        error = reference - measured
        p_term = cfg.kp * error
        if dt > 0.0:
            if self.previous_measurement is None:
                derivative = 0.0
            else:
                derivative = -(measured - self.previous_measurement) / dt
        else:
            derivative = 0.0
        d_term = cfg.kd * derivative
        ff_term = cfg.kff * feedforward

        proposed_i = self.integral + cfg.ki * error * dt
        proposed_i = _clamp(proposed_i, cfg.integral_limit)
        raw = p_term + proposed_i + d_term + ff_term
        output = _clamp(raw, cfg.output_limit)
        # Conditional integration prevents windup while still allowing recovery.
        if raw == output or error * raw <= 0.0:
            self.integral = proposed_i

        self.previous_error = error
        self.previous_measurement = measured
        self.terms = PIDTerms(p_term, self.integral, d_term, ff_term, output)
        return output


@dataclass
class ControlOutput:
    vd: float = 0.0
    vq: float = 0.0
    position_ref: float = 0.0
    speed_ref: float = 0.0  # rpm
    current_ref: float = 0.0
    active_loop: str = ""


class ServoController:
    """Implements the selectable single and cascade loop topologies."""

    def __init__(self, config: ControlConfig, motor: MotorConfig):
        self.config = config
        self.motor = motor
        self.current_q = PIDController(config.current)
        self.current_d = PIDController(config.current)
        self.speed = PIDController(config.speed)
        self.position = PIDController(config.position)

    def reset(self) -> None:
        for controller in (self.current_q, self.current_d, self.speed, self.position):
            controller.reset()

    def update(self, command: float, state: dict[str, float], dt: float) -> ControlOutput:
        mode = self.config.mode
        theta = state["theta"]
        speed_rpm = state["omega"]
        iq = state["iq"]
        id_current = state["id"]
        output = ControlOutput(active_loop=mode.value)

        if mode == LoopMode.CURRENT:
            output.current_ref = command
            current_ff = command if self.config.current_feedforward else 0.0
            output.vq = self.current_q.update(command, iq, dt, current_ff)
            output.vd = self.current_d.update(0.0, id_current, dt)
        elif mode == LoopMode.SPEED:
            output.speed_ref = command
            speed_ff = command if self.config.speed_feedforward else 0.0
            output.vq = self.speed.update(command, speed_rpm, dt, speed_ff)
        elif mode == LoopMode.POSITION:
            output.position_ref = command
            position_ff = command if self.config.position_feedforward else 0.0
            output.vq = self.position.update(command, theta, dt, position_ff)
        elif mode == LoopMode.CURRENT_SPEED:
            output.speed_ref = command
            speed_ff = command if self.config.speed_feedforward else 0.0
            output.current_ref = self.speed.update(command, speed_rpm, dt, speed_ff)
            current_ff = output.current_ref if self.config.current_feedforward else 0.0
            output.vq = self.current_q.update(output.current_ref, iq, dt, current_ff)
            output.vd = self.current_d.update(0.0, id_current, dt)
        elif mode == LoopMode.CURRENT_POSITION:
            output.position_ref = command
            position_ff = command if self.config.position_feedforward else 0.0
            output.current_ref = self.position.update(command, theta, dt, position_ff)
            current_ff = output.current_ref if self.config.current_feedforward else 0.0
            output.vq = self.current_q.update(output.current_ref, iq, dt, current_ff)
            output.vd = self.current_d.update(0.0, id_current, dt)
        elif mode == LoopMode.SPEED_POSITION:
            output.position_ref = command
            position_ff = command if self.config.position_feedforward else 0.0
            output.speed_ref = self.position.update(command, theta, dt, position_ff)
            speed_ff = output.speed_ref if self.config.speed_feedforward else 0.0
            output.vq = self.speed.update(output.speed_ref, speed_rpm, dt, speed_ff)
        else:
            output.position_ref = command
            position_ff = command if self.config.position_feedforward else 0.0
            output.speed_ref = self.position.update(command, theta, dt, position_ff)
            speed_ff = output.speed_ref if self.config.speed_feedforward else 0.0
            output.current_ref = self.speed.update(output.speed_ref, speed_rpm, dt, speed_ff)
            current_ff = output.current_ref if self.config.current_feedforward else 0.0
            output.vq = self.current_q.update(output.current_ref, iq, dt, current_ff)
            output.vd = self.current_d.update(0.0, id_current, dt)

        voltage_limit = self.motor.dc_voltage / math.sqrt(3.0)
        magnitude = math.hypot(output.vd, output.vq)
        if magnitude > voltage_limit > 0.0:
            scale = voltage_limit / magnitude
            output.vd *= scale
            output.vq *= scale
        return output


def _clamp(value: float, limit: float) -> float:
    limit = abs(limit)
    return max(-limit, min(limit, value))
