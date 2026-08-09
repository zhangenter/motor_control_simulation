from __future__ import annotations

import math


RPM_PER_RAD_S = 60.0 / (2.0 * math.pi)
RAD_S_PER_RPM = 1.0 / RPM_PER_RAD_S


def rpm_to_rad_s(speed_rpm: float) -> float:
    """Convert rotational speed from revolutions per minute to radians per second."""
    return speed_rpm * RAD_S_PER_RPM


def rad_s_to_rpm(speed_rad_s: float) -> float:
    """Convert rotational speed from radians per second to revolutions per minute."""
    return speed_rad_s * RPM_PER_RAD_S
