from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import MotorConfig
from ..control import (
    PIDTuningResult,
    tune_current_loop,
    tune_position_loop,
    tune_speed_loop,
)
from .widgets import make_double, make_int


class PIDCalculatorDialog(QDialog):
    """Model-based PID calculator for the three loops in the teaching console."""

    pid_ready = pyqtSignal(str, float, float, float)
    LOOP_KEYS = ("current", "speed", "position")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("PID 计算器 · ServoLab 工具箱")
        self.setMinimumSize(680, 610)
        self.resize(720, 650)
        self.last_result: PIDTuningResult | None = None
        self.last_loop = "current"
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(self._build_heading())
        layout.addWidget(self._build_loop_selector())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_current_page())
        self.pages.addWidget(self._build_speed_page())
        self.pages.addWidget(self._build_position_page())
        layout.addWidget(self.pages)
        layout.addWidget(self._build_results())
        layout.addLayout(self._build_actions())

    @staticmethod
    def _build_heading() -> QWidget:
        frame = QFrame()
        frame.setObjectName("TuningHeader")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(3)
        eyebrow = QLabel("TOOLBOX  /  MODEL-BASED TUNING")
        eyebrow.setObjectName("TuningEyebrow")
        title = QLabel("三环 PID 计算器")
        title.setObjectName("DialogTitle")
        summary = QLabel("根据当前电机模型与目标动态特性计算增益，并可写回实验。")
        summary.setObjectName("TuningDescription")
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(summary)
        return frame

    def _build_loop_selector(self) -> QWidget:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("计算对象")
        label.setObjectName("SectionTitle")
        self.loop_combo = QComboBox()
        self.loop_combo.addItems(["电流环", "速度环", "位置环"])
        self.loop_combo.setMinimumWidth(180)
        self.loop_context = QLabel("RL 模型  ·  A → V")
        self.loop_context.setObjectName("TuningContext")
        layout.addWidget(label)
        layout.addWidget(self.loop_combo)
        layout.addSpacing(8)
        layout.addWidget(self.loop_context)
        layout.addStretch()
        return frame

    def _build_current_page(self) -> QWidget:
        page, form = self._parameter_page(
            "电流环参数",
            "采用 RL 对象零点抵消法，目标带宽应明显低于采样频率。",
        )
        self.current_resistance = make_double(0.6, 0.000001, 1e5, 6, 0.1, " Ω")
        self.current_inductance = make_double(0.0015, 0.0000001, 100, 8, 0.0001, " H")
        self.current_bandwidth = make_double(400.0, 0.01, 1e6, 2, 10.0, " Hz")
        form.addRow("定子电阻 Rs（每相）", self.current_resistance)
        form.addRow("q 轴电感 Lq（每相等效）", self.current_inductance)
        form.addRow("目标带宽 fc", self.current_bandwidth)
        self._add_formula(form, "Kp = Lq · 2πfc     Ki = Rs · 2πfc     Kd = 0")
        return page

    def _build_speed_page(self) -> QWidget:
        page, form = self._parameter_page(
            "速度环参数",
            "采用电流到转速的机械模型和二阶极点配置，结果单位适配 rpm 反馈。",
        )
        self.speed_inertia = make_double(0.0008, 0.00000001, 100, 9, 0.0001, " kg·m²")
        self.speed_viscous = make_double(0.0001, 0, 100, 9, 0.0001, " N·m·s")
        self.speed_poles = make_int(4, 1, 100)
        self.speed_flux = make_double(0.055, 0.000001, 100, 7, 0.005, " Wb")
        self.speed_frequency = make_double(20.0, 0.01, 1e5, 2, 1.0, " Hz")
        self.speed_damping = make_double(0.707, 0.01, 10.0, 3, 0.05)
        for label, widget in (
            ("转动惯量 J", self.speed_inertia),
            ("黏性系数 B", self.speed_viscous),
            ("极对数 p", self.speed_poles),
            ("永磁磁链 ψf", self.speed_flux),
            ("目标自然频率 fn", self.speed_frequency),
            ("阻尼比 ζ", self.speed_damping),
        ):
            form.addRow(label, widget)
        self._add_formula(form, "Kt = 1.5pψf；按 s² + 2ζωn·s + ωn² 配置闭环极点")
        return page

    def _build_position_page(self) -> QWidget:
        page, form = self._parameter_page(
            "位置环参数",
            "位置外环按理想速度内环设计。工程上通常采用 P 控制，积分与微分置零。",
        )
        self.position_bandwidth = make_double(2.0, 0.001, 1e4, 3, 0.25, " Hz")
        form.addRow("目标带宽 fc", self.position_bandwidth)
        self._add_formula(form, "Kp = 2πfc · 60 / 2π     Ki = 0     Kd = 0")
        note = QLabel("建议：位置环带宽不高于速度环带宽的 1/5。")
        note.setObjectName("TuningHint")
        form.addRow("带宽配合", note)
        return page

    @staticmethod
    def _parameter_page(title: str, description: str) -> tuple[QWidget, QFormLayout]:
        page = QFrame()
        page.setObjectName("TuningPanel")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("TuningPanelTitle")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setObjectName("TuningDescription")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        outer.addWidget(title_label)
        outer.addWidget(description_label)
        outer.addSpacing(4)
        outer.addLayout(form)
        return page, form

    @staticmethod
    def _add_formula(form: QFormLayout, text: str) -> None:
        formula = QLabel(text)
        formula.setWordWrap(True)
        formula.setObjectName("TuningFormula")
        form.addRow("计算规则", formula)

    def _build_results(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TuningResults")
        layout = QGridLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setHorizontalSpacing(10)
        title = QLabel("计算结果")
        title.setObjectName("SectionTitle")
        self.result_status = QLabel("输入参数后点击“计算 PID”")
        self.result_status.setObjectName("TuningHint")
        layout.addWidget(title, 0, 0)
        layout.addWidget(self.result_status, 0, 1, 1, 2)
        self.result_labels = []
        for column, name in enumerate(("Kp", "Ki", "Kd")):
            card, value = self._result_card(name)
            self.result_labels.append(value)
            layout.addWidget(card, 1, column)
        return frame

    @staticmethod
    def _result_card(name: str) -> tuple[QWidget, QLabel]:
        card = QFrame()
        card.setObjectName("TuningResultCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(1)
        label = QLabel(name.upper())
        label.setObjectName("TuningGainName")
        value = QLabel("—")
        value.setObjectName("TuningGainValue")
        value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addWidget(value)
        return card, value

    def _build_actions(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.calculate_button = QPushButton("计算 PID")
        self.calculate_button.setObjectName("PrimaryButton")
        self.apply_button = QPushButton("应用到当前实验")
        self.apply_button.setEnabled(False)
        close_button = QPushButton("关闭")
        layout.addStretch()
        layout.addWidget(close_button)
        layout.addWidget(self.calculate_button)
        layout.addWidget(self.apply_button)
        close_button.clicked.connect(self.close)
        return layout

    def _connect_signals(self) -> None:
        self.loop_combo.currentIndexChanged.connect(self._loop_changed)
        self.calculate_button.clicked.connect(self.calculate)
        self.apply_button.clicked.connect(self.apply_result)
        for widget in self._input_widgets():
            widget.valueChanged.connect(self._invalidate_result)

    def _input_widgets(self) -> tuple[QWidget, ...]:
        return (
            self.current_resistance,
            self.current_inductance,
            self.current_bandwidth,
            self.speed_inertia,
            self.speed_viscous,
            self.speed_poles,
            self.speed_flux,
            self.speed_frequency,
            self.speed_damping,
            self.position_bandwidth,
        )

    def prepare(self, motor: MotorConfig) -> None:
        """Load current experiment motor values before showing the calculator."""

        values = (
            (self.current_resistance, motor.resistance),
            (self.current_inductance, motor.lq),
            (self.speed_inertia, motor.inertia),
            (self.speed_viscous, motor.viscous),
            (self.speed_poles, motor.pole_pairs),
            (self.speed_flux, motor.flux),
        )
        for widget, value in values:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.calculate()

    def _loop_changed(self, index: int) -> None:
        contexts = (
            "RL 模型  ·  A → V",
            "机械模型  ·  rpm → A",
            "理想速度内环  ·  rad → rpm",
        )
        self.pages.setCurrentIndex(index)
        self.loop_context.setText(contexts[index])
        self._invalidate_result()

    def _invalidate_result(self, _value=None) -> None:
        self.last_result = None
        self.apply_button.setEnabled(False)
        self.result_status.setText("参数已变更，请重新计算")

    def calculate(self) -> None:
        try:
            result = self._calculate_selected()
        except ValueError as exc:
            self.last_result = None
            self.apply_button.setEnabled(False)
            self.result_status.setText(str(exc))
            for label in self.result_labels:
                label.setText("—")
            return
        self.last_result = result
        self.last_loop = self.LOOP_KEYS[self.loop_combo.currentIndex()]
        for label, value in zip(self.result_labels, (result.kp, result.ki, result.kd)):
            label.setText(f"{value:.9g}")
        self.result_status.setText("计算完成 · 可写回当前实验")
        self.apply_button.setEnabled(True)

    def _calculate_selected(self) -> PIDTuningResult:
        index = self.loop_combo.currentIndex()
        if index == 0:
            return tune_current_loop(
                self.current_resistance.value(),
                self.current_inductance.value(),
                self.current_bandwidth.value(),
            )
        if index == 1:
            return tune_speed_loop(
                self.speed_inertia.value(),
                self.speed_viscous.value(),
                self.speed_poles.value(),
                self.speed_flux.value(),
                self.speed_frequency.value(),
                self.speed_damping.value(),
            )
        return tune_position_loop(self.position_bandwidth.value())

    def apply_result(self) -> None:
        if self.last_result is None:
            return
        result = self.last_result
        self.pid_ready.emit(self.last_loop, result.kp, result.ki, result.kd)
        self.result_status.setText("已应用到当前实验 · 控制器状态已复位")
