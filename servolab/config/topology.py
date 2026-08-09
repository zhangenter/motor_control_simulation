from enum import Enum


class LoopMode(str, Enum):
    CURRENT = "电流单环"
    SPEED = "速度单环"
    POSITION = "位置单环"
    CURRENT_SPEED = "电流-速度"
    CURRENT_POSITION = "电流-位置"
    SPEED_POSITION = "速度-位置"
    CASCADE = "电流-速度-位置"


class CommandType(str, Enum):
    STEP = "阶跃"
    RAMP = "斜坡"
    SINE = "正弦"
    TRAPEZOID = "梯形"
    S_CURVE = "S曲线"
    MANUAL = "手动给定"
    TRAJECTORY = "表格轨迹"


class ReferenceType(str, Enum):
    POSITION = "位置输入"
    SPEED = "速度输入"
    CURRENT = "电流输入"


POSITION_OUTER_MODES = frozenset(
    {
        LoopMode.POSITION,
        LoopMode.CURRENT_POSITION,
        LoopMode.SPEED_POSITION,
        LoopMode.CASCADE,
    }
)


def has_position_outer_loop(mode: LoopMode) -> bool:
    return mode in POSITION_OUTER_MODES


def allowed_reference_types(mode: LoopMode) -> tuple[ReferenceType, ...]:
    if has_position_outer_loop(mode):
        return (ReferenceType.POSITION, ReferenceType.SPEED)
    if mode in (LoopMode.SPEED, LoopMode.CURRENT_SPEED):
        return (ReferenceType.SPEED,)
    return (ReferenceType.CURRENT,)


def default_reference_type(mode: LoopMode) -> ReferenceType:
    return allowed_reference_types(mode)[0]
