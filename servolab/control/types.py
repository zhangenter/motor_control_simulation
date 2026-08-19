from dataclasses import dataclass


@dataclass
class PIDTerms:
    p: float = 0.0
    i: float = 0.0
    d: float = 0.0
    ff: float = 0.0
    output: float = 0.0


@dataclass
class ControlOutput:
    vd: float = 0.0
    vq: float = 0.0
    position_ref: float = 0.0
    speed_ref: float = 0.0  # rpm
    id_ref: float = 0.0
    iq_ref: float = 0.0
    current_ref: float = 0.0
    active_loop: str = ""
