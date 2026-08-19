from __future__ import annotations

from dataclasses import dataclass
import math

from ..config import MotorConfig
from ..units import rad_s_to_rpm, rpm_to_rad_s


@dataclass
class MotorState:
    id: float = 0.0
    iq: float = 0.0
    theta: float = 0.0
    omega: float = 0.0  # rpm
    torque: float = 0.0


class PMSMMotor:
    """Surface/interior PMSM in the rotor dq frame."""

    def __init__(self, config: MotorConfig):
        self.config = config
        self.state = MotorState()

    def reset(self) -> None:
        self.state = MotorState()

    def step(
        self,
        vd: float,
        vq: float,
        load_torque: float,
        friction_torque: float,
        extra_inertia: float,
        dt: float,
        lock_rotor: bool = False,
        back_emf_vd: float = 0.0,
        back_emf_vq: float = 0.0,
    ) -> MotorState:
        cfg = self.config
        state = self.state
        speed_rad_s = rpm_to_rad_s(state.omega)
        electrical_speed = cfg.pole_pairs * speed_rad_s
        did = (
            vd
            - cfg.resistance * state.id
            + electrical_speed * cfg.lq * state.iq
            - back_emf_vd
        ) / max(cfg.ld, 1e-9)
        diq = (
            vq
            - cfg.resistance * state.iq
            - electrical_speed * (cfg.ld * state.id + cfg.flux)
            - back_emf_vq
        ) / max(cfg.lq, 1e-9)

        state.id += did * dt
        state.iq += diq * dt
        current_magnitude = math.hypot(state.id, state.iq)
        if current_magnitude > cfg.current_limit > 0.0:
            scale = cfg.current_limit / current_magnitude
            state.id *= scale
            state.iq *= scale

        state.torque = 1.5 * cfg.pole_pairs * (
            cfg.flux * state.iq + (cfg.ld - cfg.lq) * state.id * state.iq
        )
        if lock_rotor:
            state.omega = 0.0
            return state
        inertia = max(cfg.inertia + extra_inertia, 1e-9)
        acceleration = (
            state.torque - load_torque - friction_torque - cfg.viscous * speed_rad_s
        ) / inertia
        state.omega += rad_s_to_rpm(acceleration) * dt
        state.theta += rpm_to_rad_s(state.omega) * dt
        return state

    def as_dict(self) -> dict[str, float]:
        state = self.state
        return {
            "id": state.id,
            "iq": state.iq,
            "theta": state.theta,
            "omega": state.omega,
            "torque": state.torque,
        }
