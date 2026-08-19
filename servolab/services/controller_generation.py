from __future__ import annotations

from dataclasses import dataclass
import math

from ..config import ControlConfig, CurrentAxis, LoopMode, MotorConfig, PIDConfig, ReferenceType


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

TARGET_SOURCES = {
    "position": ('reference["position"]', 'state["theta"]'),
    "speed": ('reference["speed"]', 'state["omega"]'),
    "current": ('reference["current"]', 'state["iq"]'),
}


def generate_custom_controller_code(
    mode: LoopMode,
    reference_type: ReferenceType,
    control: ControlConfig,
    motor: MotorConfig,
    options: ControllerGenerationOptions | None = None,
    current_axis: CurrentAxis = CurrentAxis.Q,
) -> str:
    generator = ControllerCodeGenerator(
        mode,
        reference_type,
        control,
        motor,
        options or ControllerGenerationOptions(),
        current_axis,
    )
    return generator.generate()


class ControllerCodeGenerator:
    def __init__(
        self,
        mode: LoopMode,
        reference_type: ReferenceType,
        control: ControlConfig,
        motor: MotorConfig,
        options: ControllerGenerationOptions,
        current_axis: CurrentAxis = CurrentAxis.Q,
    ):
        self.mode = mode
        self.reference_type = reference_type
        self.control = control
        self.motor = motor
        self.options = options
        self.current_axis = current_axis
        self.chain = LOOP_CHAINS[mode]

    def generate(self) -> str:
        lines = self._header_lines()
        lines.extend(self._pid_helper_lines())
        lines.extend(self._control_lines())
        return "\n".join(lines)

    def _header_lines(self) -> list[str]:
        feature_text = "、".join(self._enabled_features()) or "无"
        return [
            "# ServoLab 根据当前实验配置动态生成",
            f"# 控制方式：{self.mode.value}",
            f"# 控制目标：{self.reference_type.value}",
            f"# 可选功能：{feature_text}",
            "# state: id, iq, theta, omega (rpm), torque, t",
            "# reference: user_input, position, speed (rpm), current, id_ref, iq_ref",
            "",
            "def clamp(value, limit):",
            "    limit = abs(limit)",
            "    return max(-limit, min(limit, value))",
            "",
            "",
        ]

    def _enabled_features(self) -> list[str]:
        features = []
        if self.options.reference_feedforward:
            features.append("参考前馈 Kff")
        if self.options.back_emf_compensation:
            features.append("反电动势补偿")
        if self.options.dq_decoupling:
            features.append("dq 交叉耦合补偿")
        if self.options.friction_compensation:
            features.append("黏性摩擦补偿")
        if self.options.anti_windup:
            features.append("抗积分饱和")
        return features

    def _pid_helper_lines(self) -> list[str]:
        lines = [
            "def pid_step(",
            "    name, target, measured, kp, ki, kd,",
            "    output_limit, integral_limit, params, dt,",
            "    feedforward=0.0, kff=0.0,",
            "):",
            "    error = target - measured",
            '    integral_key = name + "_integral"',
            '    previous_key = name + "_previous_measurement"',
            "    integral = params.get(integral_key, 0.0)",
            "    previous = params.get(previous_key)",
            "    derivative = 0.0 if previous is None or dt <= 0.0 else -(measured - previous) / dt",
            "    proposed_integral = clamp(integral + ki * error * dt, integral_limit)",
            "    raw = kp * error + proposed_integral + kd * derivative + kff * feedforward",
            "    output = clamp(raw, output_limit)",
        ]
        if self.options.anti_windup:
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
            ]
        )
        return lines

    def _control_lines(self) -> list[str]:
        lines = ["def control(state, reference, params, dt):"]
        lines.extend(self._compensation_setup_lines())
        lines.extend(self._loop_chain_lines())
        lines.extend(self._axis_output_lines())
        lines.extend(self._output_compensation_lines())
        lines.extend(self._voltage_limit_lines())
        return lines

    def _compensation_setup_lines(self) -> list[str]:
        lines = []
        if self._needs_speed_rad_s():
            lines.append('    omega_rad_s = state["omega"] * 2.0 * math.pi / 60.0')
        if self.options.friction_compensation:
            lines.extend(
                [
                    f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(self.motor.pole_pairs)})',
                    f'    flux = params.setdefault("motor_flux", {_number(self.motor.flux)})',
                    f'    viscous = params.setdefault("motor_viscous", {_number(self.motor.viscous)})',
                    "    torque_constant = max(1.5 * pole_pairs * flux, 1e-9)",
                    "    friction_current = viscous * omega_rad_s / torque_constant",
                ]
            )
        if self._needs_speed_rad_s():
            lines.append("")
        return lines

    def _loop_chain_lines(self) -> list[str]:
        outer_loop = self.chain[0]
        source, _measurement = TARGET_SOURCES[outer_loop]
        lines = [f"    {outer_loop}_target = {source}"]
        if self.mode == LoopMode.CURRENT:
            key = "id_ref" if self.current_axis == CurrentAxis.D else "iq_ref"
            lines[0] = f'    current_target = reference.get("{key}", reference["current"])'
        if outer_loop == "position" and self.reference_type == ReferenceType.SPEED:
            lines.append("    # 速度输入已由仿真核心积分为 position 参考")
        previous_output = ""
        for index, loop_name in enumerate(self.chain):
            if index > 0:
                lines.append(f"    {loop_name}_target = {previous_output}")
            lines.extend(self._loop_lines(loop_name))
            previous_output = f"{loop_name}_output"
        return lines

    def _loop_lines(self, loop_name: str) -> list[str]:
        lines = []
        d_axis_test = (
            loop_name == "current"
            and self.mode == LoopMode.CURRENT
            and self.current_axis == CurrentAxis.D
        )
        if loop_name == "current":
            if self.options.friction_compensation and not d_axis_test:
                lines.append("    current_target += friction_current")
            lines.append(
                f'    current_target = clamp(current_target, params.setdefault("current_limit", {_number(self.motor.current_limit)}))'
            )
        config = self.control.current_d if d_axis_test else getattr(self.control, loop_name)
        measurement = 'state["id"]' if d_axis_test else TARGET_SOURCES[loop_name][1]
        lines.extend(_pid_call_lines(loop_name, measurement, config, self.options))
        return lines

    def _axis_output_lines(self) -> list[str]:
        if "current" not in self.chain:
            return ["    vd = 0.0", f"    vq = {self.chain[-1]}_output"]
        d_current = self.control.current_d
        if self.mode == LoopMode.CURRENT and self.current_axis == CurrentAxis.D:
            return ["    vd = current_output", "    vq = 0.0"]
        return [
            "    # 带电流环时同时稳定 d 轴电流",
            f'    current_d_kp = params.setdefault("current_d_kp", {_number(d_current.kp)})',
            f'    current_d_ki = params.setdefault("current_d_ki", {_number(d_current.ki)})',
            f'    current_d_kd = params.setdefault("current_d_kd", {_number(d_current.kd)})',
            "    vd = pid_step(",
            '        "current_d", 0.0, state["id"], current_d_kp, current_d_ki, current_d_kd,',
            f"        {_number(d_current.output_limit)}, {_number(d_current.integral_limit)}, params, dt,",
            "    )",
            "    vq = current_output",
        ]

    def _output_compensation_lines(self) -> list[str]:
        lines = []
        if self.options.friction_compensation and "current" not in self.chain:
            lines.extend(
                [
                    f'    resistance = params.setdefault("motor_resistance", {_number(self.motor.resistance)})',
                    "    vq += resistance * friction_current",
                ]
            )
        if self.options.back_emf_compensation:
            if not self.options.friction_compensation:
                lines.extend(self._motor_flux_lines())
            lines.extend(["    # q 轴反电动势补偿", "    vq += pole_pairs * flux * omega_rad_s"])
        if self.options.dq_decoupling:
            if not (self.options.friction_compensation or self.options.back_emf_compensation):
                lines.append(
                    f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(self.motor.pole_pairs)})'
                )
            lines.extend(
                [
                    f'    ld = params.setdefault("motor_ld", {_number(self.motor.ld)})',
                    f'    lq = params.setdefault("motor_lq", {_number(self.motor.lq)})',
                    "    # dq 交叉耦合解耦",
                    '    vd -= pole_pairs * omega_rad_s * lq * state["iq"]',
                    '    vq += pole_pairs * omega_rad_s * ld * state["id"]',
                ]
            )
        return lines

    def _motor_flux_lines(self) -> list[str]:
        return [
            f'    pole_pairs = params.setdefault("motor_pole_pairs", {_number(self.motor.pole_pairs)})',
            f'    flux = params.setdefault("motor_flux", {_number(self.motor.flux)})',
        ]

    def _voltage_limit_lines(self) -> list[str]:
        voltage_limit = self.motor.dc_voltage / math.sqrt(3.0)
        return [
            f'    voltage_limit = params.setdefault("voltage_limit", {_number(voltage_limit)})',
            "    magnitude = math.hypot(vd, vq)",
            "    if magnitude > voltage_limit > 0.0:",
            "        scale = voltage_limit / magnitude",
            "        vd, vq = vd * scale, vq * scale",
            '    return {"vd": vd, "vq": vq}',
            "",
        ]

    def _needs_speed_rad_s(self) -> bool:
        return (
            self.options.back_emf_compensation
            or self.options.dq_decoupling
            or self.options.friction_compensation
        )


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
