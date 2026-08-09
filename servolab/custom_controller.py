from __future__ import annotations

from dataclasses import dataclass
import math
import multiprocessing as mp
from multiprocessing.connection import Connection
from typing import Any

from .config import ControlConfig, LoopMode, MotorConfig, PIDConfig, ReferenceType


@dataclass(frozen=True)
class ControllerGenerationOptions:
    reference_feedforward: bool = False
    back_emf_compensation: bool = False
    dq_decoupling: bool = False
    friction_compensation: bool = False
    anti_windup: bool = True


LOOP_CHAINS = {
    LoopMode.CURRENT: ("current",),
    LoopMode.SPEED: ("speed",),
    LoopMode.POSITION: ("position",),
    LoopMode.CURRENT_SPEED: ("speed", "current"),
    LoopMode.CURRENT_POSITION: ("position", "current"),
    LoopMode.SPEED_POSITION: ("position", "speed"),
    LoopMode.CASCADE: ("position", "speed", "current"),
}


def generate_custom_controller_code(
    mode: LoopMode,
    reference_type: ReferenceType,
    control: ControlConfig,
    motor: MotorConfig,
    options: ControllerGenerationOptions | None = None,
) -> str:
    """Generate an editable controller matching the current experiment topology."""
    options = options or ControllerGenerationOptions()
    chain = LOOP_CHAINS[mode]
    enabled_features = []
    if options.reference_feedforward:
        enabled_features.append("参考前馈 Kff")
    if options.back_emf_compensation:
        enabled_features.append("反电动势补偿")
    if options.dq_decoupling:
        enabled_features.append("dq 交叉耦合补偿")
    if options.friction_compensation:
        enabled_features.append("黏性摩擦补偿")
    if options.anti_windup:
        enabled_features.append("抗积分饱和")
    feature_text = "、".join(enabled_features) if enabled_features else "无"

    lines = [
        "# ServoLab 根据当前实验配置动态生成",
        f"# 控制方式：{mode.value}",
        f"# 控制目标：{reference_type.value}",
        f"# 可选功能：{feature_text}",
        "# state: id, iq, theta, omega (rpm), torque, t",
        "# reference: user_input, position, speed (rpm), current",
        "",
        "def clamp(value, limit):",
        "    limit = abs(limit)",
        "    return max(-limit, min(limit, value))",
        "",
        "",
        "def pid_step(",
        "    name, target, measured, kp, ki, kd,",
        "    output_limit, integral_limit, params, dt,",
        "    feedforward=0.0, kff=0.0,",
        "):",
        "    error = target - measured",
        "    integral_key = name + \"_integral\"",
        "    previous_key = name + \"_previous_measurement\"",
        "    integral = params.get(integral_key, 0.0)",
        "    previous = params.get(previous_key)",
        "    derivative = 0.0 if previous is None or dt <= 0.0 else -(measured - previous) / dt",
        "    proposed_integral = clamp(integral + ki * error * dt, integral_limit)",
        "    raw = kp * error + proposed_integral + kd * derivative + kff * feedforward",
        "    output = clamp(raw, output_limit)",
    ]
    if options.anti_windup:
        lines.extend(
            [
                "    # 条件积分：饱和时仅允许能促进恢复的积分方向",
                "    if raw == output or error * raw <= 0.0:",
                "        params[integral_key] = proposed_integral",
            ]
        )
    else:
        lines.append("    params[integral_key] = proposed_integral")
    lines.extend(
        [
            "    params[previous_key] = measured",
            "    return output",
            "",
            "",
            "def control(state, reference, params, dt):",
        ]
    )

    needs_omega_rad_s = (
        options.back_emf_compensation
        or options.dq_decoupling
        or options.friction_compensation
    )
    if needs_omega_rad_s:
        lines.append('    omega_rad_s = state["omega"] * 2.0 * math.pi / 60.0')
    if options.friction_compensation:
        lines.extend(
            [
                f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(motor.pole_pairs)})',
                f'    flux = params.setdefault("motor_flux", {_number(motor.flux)})',
                f'    viscous = params.setdefault("motor_viscous", {_number(motor.viscous)})',
                "    torque_constant = max(1.5 * pole_pairs * flux, 1e-9)",
                "    friction_current = viscous * omega_rad_s / torque_constant",
            ]
        )
    if needs_omega_rad_s:
        lines.append("")

    outer_loop = chain[0]
    target_sources = {
        "position": ('reference["position"]', 'state["theta"]'),
        "speed": ('reference["speed"]', 'state["omega"]'),
        "current": ('reference["current"]', 'state["iq"]'),
    }
    source, _measurement = target_sources[outer_loop]
    lines.append(f"    {outer_loop}_target = {source}")
    if outer_loop == "position" and reference_type == ReferenceType.SPEED:
        lines.append("    # 速度输入已由仿真核心积分为 position 参考")

    previous_output = ""
    for index, loop_name in enumerate(chain):
        if index > 0:
            lines.append(f"    {loop_name}_target = {previous_output}")
        if loop_name == "current":
            if options.friction_compensation:
                lines.append("    current_target += friction_current")
            lines.append(
                f'    current_target = clamp(current_target, params.setdefault("current_limit", {_number(motor.current_limit)}))'
            )
        lines.extend(_pid_call_lines(loop_name, target_sources[loop_name][1], _pid_config(control, loop_name), options))
        previous_output = f"{loop_name}_output"

    if "current" in chain:
        current = control.current
        lines.extend(
            [
                "    # 带电流环时同时稳定 d 轴电流",
                f'    current_d_kp = params.setdefault("current_d_kp", {_number(current.kp)})',
                f'    current_d_ki = params.setdefault("current_d_ki", {_number(current.ki)})',
                f'    current_d_kd = params.setdefault("current_d_kd", {_number(current.kd)})',
                "    vd = pid_step(",
                '        "current_d", 0.0, state["id"], current_d_kp, current_d_ki, current_d_kd,',
                f"        {_number(current.output_limit)}, {_number(current.integral_limit)}, params, dt,",
                "    )",
                "    vq = current_output",
            ]
        )
    else:
        lines.extend(["    vd = 0.0", f"    vq = {previous_output}"])

    if options.friction_compensation and "current" not in chain:
        lines.extend(
            [
                f'    resistance = params.setdefault("motor_resistance", {_number(motor.resistance)})',
                "    vq += resistance * friction_current",
            ]
        )
    if options.back_emf_compensation:
        if not options.friction_compensation:
            lines.extend(
                [
                    f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(motor.pole_pairs)})',
                    f'    flux = params.setdefault("motor_flux", {_number(motor.flux)})',
                ]
            )
        lines.extend(
            [
                "    # q 轴反电动势补偿",
                "    vq += pole_pairs * flux * omega_rad_s",
            ]
        )
    if options.dq_decoupling:
        if not (options.friction_compensation or options.back_emf_compensation):
            lines.append(f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(motor.pole_pairs)})')
        lines.extend(
            [
                f'    ld = params.setdefault("motor_ld", {_number(motor.ld)})',
                f'    lq = params.setdefault("motor_lq", {_number(motor.lq)})',
                "    # dq 交叉耦合解耦",
                '    vd -= pole_pairs * omega_rad_s * lq * state["iq"]',
                '    vq += pole_pairs * omega_rad_s * ld * state["id"]',
            ]
        )

    voltage_limit = motor.dc_voltage / math.sqrt(3.0)
    lines.extend(
        [
            f'    voltage_limit = params.setdefault("voltage_limit", {_number(voltage_limit)})',
            "    magnitude = math.hypot(vd, vq)",
            "    if magnitude > voltage_limit > 0.0:",
            "        scale = voltage_limit / magnitude",
            "        vd, vq = vd * scale, vq * scale",
            '    return {"vd": vd, "vq": vq}',
            "",
        ]
    )
    return "\n".join(lines)


def _pid_config(control: ControlConfig, loop_name: str) -> PIDConfig:
    return getattr(control, loop_name)


def _pid_call_lines(
    loop_name: str,
    measurement: str,
    config: PIDConfig,
    options: ControllerGenerationOptions,
) -> list[str]:
    lines = [
        f'    {loop_name}_kp = params.setdefault("{loop_name}_kp", {_number(config.kp)})',
        f'    {loop_name}_ki = params.setdefault("{loop_name}_ki", {_number(config.ki)})',
        f'    {loop_name}_kd = params.setdefault("{loop_name}_kd", {_number(config.kd)})',
    ]
    if options.reference_feedforward:
        lines.append(f'    {loop_name}_kff = params.setdefault("{loop_name}_kff", {_number(config.kff)})')
    lines.extend(
        [
            f"    {loop_name}_output = pid_step(",
            f'        "{loop_name}", {loop_name}_target, {measurement},',
            f"        {loop_name}_kp, {loop_name}_ki, {loop_name}_kd,",
            f"        {_number(config.output_limit)}, {_number(config.integral_limit)}, params, dt,",
        ]
    )
    if options.reference_feedforward:
        lines.append(f"        {loop_name}_target, {loop_name}_kff,")
    lines.extend(["    )", ""])
    return lines


def _number(value: float | int) -> str:
    return f"{float(value):.12g}"


class CustomControllerError(RuntimeError):
    pass


class CustomControllerProcess:
    def __init__(self, timeout_s: float = 0.05):
        self.timeout_s = timeout_s
        self.process: mp.Process | None = None
        self.connection: Connection | None = None

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.is_alive())

    def start(self, code: str) -> None:
        self.stop()
        parent, child = mp.Pipe()
        self.process = mp.Process(target=_worker, args=(child, code), daemon=True)
        self.process.start()
        self.connection = parent
        if not parent.poll(self.timeout_s * 10.0):
            self.stop()
            raise CustomControllerError("自定义控制器启动超时")
        message = parent.recv()
        if message.get("status") != "ready":
            self.stop()
            raise CustomControllerError(message.get("error", "自定义控制器编译失败"))

    def update(
        self,
        state: dict[str, float],
        reference: dict[str, float],
        dt: float,
    ) -> tuple[float, float]:
        if not self.running or self.connection is None:
            raise CustomControllerError("自定义控制器尚未启动")
        self.connection.send({"command": "step", "state": state, "reference": reference, "dt": dt})
        if not self.connection.poll(self.timeout_s):
            self.stop()
            raise CustomControllerError(f"自定义控制器单步响应超过 {self.timeout_s * 1000:.0f} ms")
        message = self.connection.recv()
        if message.get("status") != "ok":
            raise CustomControllerError(message.get("error", "自定义控制器执行失败"))
        return float(message["vd"]), float(message["vq"])

    def stop(self) -> None:
        if self.connection is not None:
            try:
                self.connection.send({"command": "stop"})
            except (BrokenPipeError, EOFError, OSError):
                pass
            self.connection.close()
        if self.process is not None:
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.2)
        self.connection = None
        self.process = None


def _worker(connection: Connection, code: str) -> None:
    safe_builtins = {
        "abs": abs,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "pow": pow,
        "range": range,
        "round": round,
        "sum": sum,
        "tuple": tuple,
    }
    namespace: dict[str, Any] = {"__builtins__": safe_builtins, "math": math}
    params: dict[str, Any] = {}
    try:
        exec(compile(code, "<custom-controller>", "exec"), namespace, namespace)
        controller = namespace.get("control")
        if not callable(controller):
            raise ValueError("代码必须定义 control(state, reference, params, dt) 函数")
    except Exception as exc:  # noqa: BLE001 - error crosses process boundary
        connection.send({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        connection.close()
        return
    connection.send({"status": "ready"})
    while True:
        try:
            message = connection.recv()
        except EOFError:
            break
        if message.get("command") == "stop":
            break
        try:
            result = controller(message["state"], message["reference"], params, float(message["dt"]))
            if isinstance(result, dict):
                vd, vq = float(result.get("vd", 0.0)), float(result.get("vq", 0.0))
            else:
                vd, vq = 0.0, float(result)
            if not math.isfinite(vd) or not math.isfinite(vq):
                raise ValueError("控制器输出必须是有限数值")
            connection.send({"status": "ok", "vd": vd, "vq": vq})
        except Exception as exc:  # noqa: BLE001
            connection.send({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    connection.close()
