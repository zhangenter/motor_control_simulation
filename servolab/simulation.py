from __future__ import annotations

import math
from typing import Callable

from .commands import command_value
from .config import ExperimentConfig, LoopMode, ReferenceType, has_position_outer_loop
from .controllers import ControlOutput, ServoController
from .custom_controller import CustomControllerProcess
from .disturbances import DisturbanceModel
from .history import SimulationHistory
from .motor import PMSMMotor
from .units import rpm_to_rad_s


class ServoSimulation:
    def __init__(self, config: ExperimentConfig | None = None):
        self.config = config or ExperimentConfig()
        self.custom_controller: CustomControllerProcess | None = None
        self.use_custom_controller = False
        self.time = 0.0
        self._sample_accumulator = 0.0
        self._integrated_position_ref = 0.0
        self._reference_signature: tuple[LoopMode, ReferenceType] | None = None
        self._build_components()
        self.history = SimulationHistory()
        self.last_sample: dict[str, float] = {}

    def _build_components(self) -> None:
        cfg = self.config
        self.motor = PMSMMotor(cfg.motor)
        self.controller = ServoController(cfg.control, cfg.motor)
        self.disturbance = DisturbanceModel(
            cfg.disturbance, cfg.motor, cfg.simulation.dt, cfg.simulation.random_seed
        )

    def apply_config(self, config: ExperimentConfig, reset: bool = True) -> None:
        self.config = config
        self._build_components()
        if reset:
            self.reset()

    def reset(self) -> None:
        self.time = 0.0
        self._sample_accumulator = 0.0
        self._integrated_position_ref = self.motor.state.theta
        self._reference_signature = None
        self.motor.reset()
        self.controller.reset()
        self.disturbance.reset(self.config.simulation.random_seed)
        self.history.clear()
        self.last_sample = {}
        self._record_sample(0.0, ControlOutput(active_loop=self.config.control.mode.value), 0.0, 0.0, 0.0)

    def step(self, steps: int = 1) -> dict[str, float]:
        for _ in range(max(steps, 1)):
            self._step_once()
        return self.last_sample

    def _step_once(self) -> None:
        cfg = self.config
        dt = cfg.simulation.dt
        state = self.motor.state
        measured_theta, measured_speed_rpm = self.disturbance.encoder(state.theta, state.omega)
        measured = self.motor.as_dict()
        measured["theta"] = measured_theta
        measured["omega"] = measured_speed_rpm
        measured["t"] = self.time
        user_command = command_value(cfg.command, self.time)
        control_command = self._controller_command(user_command, measured["theta"], dt)
        control = self.controller.update(control_command, measured, dt)

        if self.use_custom_controller and self.custom_controller is not None:
            reference = {
                "command": control_command,
                "user_input": user_command,
                "position": control.position_ref,
                "speed": control.speed_ref,
                "current": control.current_ref if cfg.control.mode != LoopMode.CURRENT else control_command,
            }
            vd, vq = self.custom_controller.update(measured, reference, dt)
            voltage_limit = cfg.motor.dc_voltage / math.sqrt(3.0)
            magnitude = math.hypot(vd, vq)
            if magnitude > voltage_limit > 0.0:
                scale = voltage_limit / magnitude
                vd, vq = vd * scale, vq * scale
            control.vd, control.vq = vd, vq
            control.active_loop = "自定义控制器"

        cogging = self.disturbance.cogging(state.theta)
        friction = self.disturbance.friction(state.omega, state.torque)
        external_load = self.disturbance.load(self.time)
        total_load = external_load + cogging
        extra_inertia = self.disturbance.inertia(self.time)
        self.motor.step(control.vd, control.vq, total_load, friction, extra_inertia, dt)
        self.time += dt
        self._sample_accumulator += dt
        if self._sample_accumulator + 1e-12 >= cfg.simulation.plot_interval:
            self._sample_accumulator %= max(cfg.simulation.plot_interval, dt)
            self._record_sample(user_command, control, external_load, friction, cogging)

    def _controller_command(self, user_command: float, measured_position: float, dt: float) -> float:
        """Adapt the user-selected physical input to the active outer loop."""
        mode = self.config.control.mode
        reference_type = self.config.command.reference_type
        signature = (mode, reference_type)
        if signature != self._reference_signature:
            if reference_type == ReferenceType.SPEED and has_position_outer_loop(mode):
                self._integrated_position_ref = measured_position
            self._reference_signature = signature

        if reference_type == ReferenceType.SPEED and has_position_outer_loop(mode):
            self._integrated_position_ref += rpm_to_rad_s(user_command) * dt
            return self._integrated_position_ref
        return user_command

    def _record_sample(
        self,
        command: float,
        control: ControlOutput,
        load: float,
        friction: float,
        cogging: float,
    ) -> None:
        state = self.motor.state
        mode = self.config.control.mode
        reference_type = self.config.command.reference_type
        position_error = control.position_ref - state.theta if "位置" in mode.value else 0.0
        speed_error = control.speed_ref - state.omega if "速度" in mode.value else 0.0
        target_current = control.current_ref if mode != LoopMode.CURRENT else command
        current_error = target_current - state.iq if "电流" in mode.value else 0.0
        active_pid = self._active_pid_terms()
        sample = {
            "time": self.time,
            "command": command,
            "position_ref": control.position_ref,
            "position": state.theta,
            "position_error": position_error,
            "user_speed_ref": command if reference_type == ReferenceType.SPEED else 0.0,
            "speed_ref": control.speed_ref,
            "speed": state.omega,
            "speed_error": speed_error,
            "current_ref": target_current,
            "id": state.id,
            "iq": state.iq,
            "current_error": current_error,
            "torque": state.torque,
            "load_torque": load,
            "friction_torque": friction,
            "cogging_torque": cogging,
            "vd": control.vd,
            "vq": control.vq,
            "pid_p": active_pid.p,
            "pid_i": active_pid.i,
            "pid_d": active_pid.d,
        }
        self.last_sample = sample
        self.history.append(sample)

    def _active_pid_terms(self):
        mode = self.config.control.mode
        if mode == LoopMode.CURRENT:
            return self.controller.current_q.terms
        if mode in (LoopMode.SPEED, LoopMode.CURRENT_SPEED):
            return self.controller.speed.terms
        return self.controller.position.terms

    def run_offline(
        self,
        duration: float | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> SimulationHistory:
        self.reset()
        final_time = duration if duration is not None else self.config.simulation.duration
        total_steps = max(int(math.ceil(final_time / self.config.simulation.dt)), 1)
        report_interval = max(total_steps // 100, 1)
        for index in range(total_steps):
            self._step_once()
            if progress and index % report_interval == 0:
                progress(index / total_steps)
        if progress:
            progress(1.0)
        return self.history
