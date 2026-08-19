from __future__ import annotations

import math

from ..config import ControlConfig, CurrentAxis, LoopMode, MotorConfig
from .pid import PIDController
from .types import ControlOutput


class ServoController:
    """Implements the selectable single and cascade loop topologies."""

    def __init__(self, config: ControlConfig, motor: MotorConfig):
        self.config = config
        self.motor = motor
        self.current_q = PIDController(config.current)
        self.current_d = PIDController(config.current_d)
        self.speed = PIDController(config.speed)
        self.position = PIDController(config.position)

    def reset(self) -> None:
        for controller in (self.current_q, self.current_d, self.speed, self.position):
            controller.reset()

    def update(
        self,
        command: float,
        state: dict[str, float],
        dt: float,
        current_axis: CurrentAxis = CurrentAxis.Q,
    ) -> ControlOutput:
        mode = self.config.mode
        output = ControlOutput(active_loop=mode.value)
        if mode == LoopMode.CURRENT:
            if current_axis == CurrentAxis.D:
                self._current_loop(output, 0.0, state, dt, id_target=command)
            else:
                self._current_loop(output, command, state, dt)
        elif mode == LoopMode.SPEED:
            self._speed_voltage_loop(output, command, state, dt)
        elif mode == LoopMode.POSITION:
            self._position_voltage_loop(output, command, state, dt)
        elif mode == LoopMode.CURRENT_SPEED:
            self._speed_current_loop(output, command, state, dt)
        elif mode == LoopMode.CURRENT_POSITION:
            output.position_ref = command
            output.current_ref = self._position_output(command, state["theta"], dt)
            self._current_loop(output, output.current_ref, state, dt)
        elif mode == LoopMode.SPEED_POSITION:
            output.position_ref = command
            output.speed_ref = self._position_output(command, state["theta"], dt)
            self._speed_voltage_loop(output, output.speed_ref, state, dt)
        else:
            output.position_ref = command
            output.speed_ref = self._position_output(command, state["theta"], dt)
            self._speed_current_loop(output, output.speed_ref, state, dt)
        self._limit_voltage(output)
        return output

    def _current_loop(
        self,
        output: ControlOutput,
        target: float,
        state: dict[str, float],
        dt: float,
        id_target: float = 0.0,
    ) -> None:
        output.id_ref = id_target
        output.iq_ref = target
        output.current_ref = target
        q_feedforward = target if self.config.current_feedforward else 0.0
        d_feedforward = id_target if self.config.current_feedforward else 0.0
        output.vq = self.current_q.update(target, state["iq"], dt, q_feedforward)
        output.vd = self.current_d.update(id_target, state["id"], dt, d_feedforward)

    def _speed_voltage_loop(
        self,
        output: ControlOutput,
        target: float,
        state: dict[str, float],
        dt: float,
    ) -> None:
        output.speed_ref = target
        feedforward = target if self.config.speed_feedforward else 0.0
        output.vq = self.speed.update(target, state["omega"], dt, feedforward)

    def _position_voltage_loop(
        self,
        output: ControlOutput,
        target: float,
        state: dict[str, float],
        dt: float,
    ) -> None:
        output.position_ref = target
        output.vq = self._position_output(target, state["theta"], dt)

    def _speed_current_loop(
        self,
        output: ControlOutput,
        target: float,
        state: dict[str, float],
        dt: float,
    ) -> None:
        output.speed_ref = target
        feedforward = target if self.config.speed_feedforward else 0.0
        output.current_ref = self.speed.update(target, state["omega"], dt, feedforward)
        self._current_loop(output, output.current_ref, state, dt)

    def _position_output(self, target: float, measured: float, dt: float) -> float:
        feedforward = target if self.config.position_feedforward else 0.0
        return self.position.update(target, measured, dt, feedforward)

    def _limit_voltage(self, output: ControlOutput) -> None:
        voltage_limit = self.motor.dc_voltage / math.sqrt(3.0)
        magnitude = math.hypot(output.vd, output.vq)
        if magnitude > voltage_limit > 0.0:
            scale = voltage_limit / magnitude
            output.vd *= scale
            output.vq *= scale
