from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from pyqtgraph.exporters import ImageExporter
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QSyntaxHighlighter
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .commands import load_trajectory_csv
from .config import (
    CommandType,
    ExperimentConfig,
    LoopMode,
    ReferenceType,
    allowed_reference_types,
    default_reference_type,
    has_position_outer_loop,
)
from .custom_controller import (
    ControllerGenerationOptions,
    CustomControllerError,
    CustomControllerProcess,
    generate_custom_controller_code,
)
from .simulation import ServoSimulation
from .theme import APP_STYLE, PLOT_COLORS
from .ui_widgets import (
    PIDEditor,
    PlotDashboard,
    TopologyWidget,
    ValueCard,
    make_double,
    make_int,
)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        import re

        self.rules = []
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#e5b85c"))
        keyword_format.setFontWeight(QFont.Bold)
        for word in (
            "def", "return", "if", "else", "elif", "for", "while", "in", "and", "or", "not",
            "True", "False", "None", "try", "except", "raise", "class", "from", "import",
        ):
            self.rules.append((re.compile(rf"\b{word}\b"), keyword_format))
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#6fbee8"))
        self.rules.append((re.compile(r"\b\d+(?:\.\d+)?\b"), number_format))
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#60777e"))
        self.rules.append((re.compile(r"#.*$"), comment_format))
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#72d5a8"))
        self.rules.append((re.compile(r"(['\"])(?:(?!\1).)*\1"), string_format))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for pattern, text_format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)


class ServoLabWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ServoLab · PMSM 伺服电机控制示教器")
        self.resize(1540, 960)
        self.setMinimumSize(1180, 760)
        self.config = ExperimentConfig()
        self.simulation = ServoSimulation(self.config)
        self.custom_process = CustomControllerProcess(timeout_s=0.04)
        self.simulation.custom_controller = self.custom_process
        self.running = False
        self.overlays: list[tuple[str, dict[str, list[float]]]] = []
        self._last_wall_time = time.perf_counter()
        self._updating_form = False
        self._build_ui()
        self._connect_shortcuts()
        self._load_form_from_config()
        self.simulation.reset()
        self._refresh_ui()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._simulation_tick)
        self.timer.start()
        self._log("系统就绪。选择控制拓扑和实验参数后开始运行。")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        vertical = QSplitter(Qt.Vertical)
        horizontal = QSplitter(Qt.Horizontal)
        horizontal.addWidget(self._build_left_panel())
        horizontal.addWidget(self._build_center_panel())
        horizontal.addWidget(self._build_right_panel())
        horizontal.setStretchFactor(0, 0)
        horizontal.setStretchFactor(1, 1)
        horizontal.setStretchFactor(2, 0)
        horizontal.setSizes([330, 900, 260])
        vertical.addWidget(horizontal)
        vertical.addWidget(self._build_bottom_panel())
        vertical.setStretchFactor(0, 1)
        vertical.setStretchFactor(1, 0)
        vertical.setSizes([720, 220])
        root_layout.addWidget(vertical)
        self.setCentralWidget(root)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.status_message = QLabel("READY")
        self.status_message.setObjectName("StatusStopped")
        self.sample_status = QLabel("dt 200 μs  ·  plot 2 ms")
        status.addWidget(self.status_message)
        status.addPermanentWidget(self.sample_status)
        self.setStatusBar(status)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(72)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 8, 18, 8)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand = QLabel("SERVOLAB")
        brand.setObjectName("Brand")
        sub = QLabel("PMSM CONTROL TEACHING CONSOLE  /  01")
        sub.setObjectName("BrandSub")
        brand_box.addWidget(brand)
        brand_box.addWidget(sub)
        layout.addLayout(brand_box)
        layout.addSpacing(28)

        self.run_button = QPushButton("▶  运行")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.setToolTip("运行或继续实时仿真（Space）")
        self.pause_button = QPushButton("Ⅱ  暂停")
        self.step_button = QPushButton("›|  单步")
        self.reset_button = QPushButton("↺  复位")
        self.offline_button = QPushButton("⚡  离线仿真")
        self.compare_button = QPushButton("＋  保留对比")
        for button in (
            self.run_button, self.pause_button, self.step_button, self.reset_button,
            self.offline_button, self.compare_button,
        ):
            layout.addWidget(button)
        layout.addStretch()

        self.open_button = QToolButton()
        self.open_button.setText("打开")
        self.save_button = QToolButton()
        self.save_button.setText("保存")
        self.export_button = QToolButton()
        self.export_button.setText("导出")
        layout.addWidget(self.open_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.export_button)

        self.run_button.clicked.connect(self.start_simulation)
        self.pause_button.clicked.connect(self.pause_simulation)
        self.step_button.clicked.connect(self.single_step)
        self.reset_button.clicked.connect(self.reset_simulation)
        self.offline_button.clicked.connect(self.run_offline)
        self.compare_button.clicked.connect(self.keep_comparison)
        self.open_button.clicked.connect(self.load_experiment)
        self.save_button.clicked.connect(self.save_experiment)
        self.export_button.clicked.connect(self.export_data_menu)
        return header

    def _scroll_tab(self, content: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(content)
        return area

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(400)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(10, 10, 8, 8)
        title = QLabel("实验参数")
        title.setObjectName("SectionTitle")
        outer.addWidget(title)
        self.parameter_tabs = QTabWidget()
        self.parameter_tabs.addTab(self._scroll_tab(self._build_experiment_form()), "实验")
        self.parameter_tabs.addTab(self._scroll_tab(self._build_motor_form()), "电机")
        self.parameter_tabs.addTab(self._scroll_tab(self._build_pid_form()), "PID")
        self.parameter_tabs.addTab(self._scroll_tab(self._build_disturbance_form()), "干扰")
        outer.addWidget(self.parameter_tabs)
        return panel

    def _build_experiment_form(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 16)
        topology_group = QGroupBox("控制拓扑")
        topology_form = QFormLayout(topology_group)
        self.experiment_name = QLineEdit(self.config.name)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([item.value for item in LoopMode])
        self.reference_combo = QComboBox()
        self.reference_combo.addItems([item.value for item in ReferenceType])
        topology_form.addRow("实验名称", self.experiment_name)
        topology_form.addRow("控制方式", self.mode_combo)
        topology_form.addRow("用户输入", self.reference_combo)
        layout.addWidget(topology_group)

        command_group = QGroupBox("指令发生器")
        command_form = QFormLayout(command_group)
        self.command_combo = QComboBox()
        self.command_combo.addItems([item.value for item in CommandType])
        self.command_amplitude = make_double(6.283185307, -1e5, 1e5, 5, 0.5)
        self.command_offset = make_double(0, -1e5, 1e5, 5, 0.1)
        self.command_frequency = make_double(0.5, 0, 1e4, 4, 0.1, " Hz")
        self.command_start = make_double(0.2, 0, 1e4, 4, 0.1, " s")
        self.command_rise = make_double(0.5, 0.0001, 1e4, 4, 0.1, " s")
        self.command_hold = make_double(1.0, 0, 1e4, 4, 0.1, " s")
        self.command_manual = make_double(0, -1e5, 1e5, 5, 0.1)
        self.trajectory_button = QPushButton("载入 time,value CSV…")
        for label, widget in (
            ("波形", self.command_combo), ("幅值", self.command_amplitude),
            ("偏置", self.command_offset), ("频率", self.command_frequency),
            ("起始时刻", self.command_start), ("上升时间", self.command_rise),
            ("保持时间", self.command_hold), ("手动值", self.command_manual),
        ):
            command_form.addRow(label, widget)
        command_form.addRow("轨迹文件", self.trajectory_button)
        layout.addWidget(command_group)

        sim_group = QGroupBox("时间与采样")
        sim_form = QFormLayout(sim_group)
        self.sim_dt = make_double(0.0002, 0.00001, 0.1, 6, 0.0001, " s")
        self.sim_duration = make_double(4.0, 0.01, 3600, 3, 1, " s")
        self.plot_interval = make_double(0.002, 0.0001, 1, 5, 0.001, " s")
        self.realtime_factor = make_double(1.0, 0.01, 50, 2, 0.25, " ×")
        sim_form.addRow("仿真步长", self.sim_dt)
        sim_form.addRow("实验时长", self.sim_duration)
        sim_form.addRow("记录间隔", self.plot_interval)
        sim_form.addRow("实时倍率", self.realtime_factor)
        layout.addWidget(sim_group)
        layout.addStretch()

        self.mode_combo.currentTextChanged.connect(self._form_changed)
        self.reference_combo.currentTextChanged.connect(self._form_changed)
        self.command_combo.currentTextChanged.connect(self._form_changed)
        self.experiment_name.editingFinished.connect(self._form_changed)
        for widget in (
            self.command_amplitude, self.command_offset, self.command_frequency, self.command_start,
            self.command_rise, self.command_hold, self.command_manual, self.sim_dt,
            self.sim_duration, self.plot_interval, self.realtime_factor,
        ):
            widget.valueChanged.connect(self._form_changed)
        self.trajectory_button.clicked.connect(self.load_trajectory)
        return content

    def _build_motor_form(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 16)
        electrical = QGroupBox("dq 电气模型")
        form = QFormLayout(electrical)
        self.motor_r = make_double(0.6, 0.00001, 1e4, 6, 0.1, " Ω")
        self.motor_ld = make_double(0.0015, 0.000001, 10, 7, 0.0001, " H")
        self.motor_lq = make_double(0.0015, 0.000001, 10, 7, 0.0001, " H")
        self.motor_flux = make_double(0.055, 0.000001, 100, 6, 0.005, " Wb")
        self.motor_poles = make_int(4, 1, 100)
        for label, widget in (
            ("定子电阻 Rs", self.motor_r), ("d 轴电感 Ld", self.motor_ld),
            ("q 轴电感 Lq", self.motor_lq), ("永磁磁链 ψf", self.motor_flux),
            ("极对数 p", self.motor_poles),
        ):
            form.addRow(label, widget)
        layout.addWidget(electrical)
        mechanical = QGroupBox("机械与执行器")
        form2 = QFormLayout(mechanical)
        self.motor_inertia = make_double(0.0008, 0.00000001, 100, 8, 0.0001, " kg·m²")
        self.motor_viscous = make_double(0.0001, 0, 100, 8, 0.0001, " N·m·s")
        self.motor_voltage = make_double(48, 0.1, 10000, 3, 1, " V")
        self.motor_current = make_double(15, 0.01, 10000, 3, 1, " A")
        form2.addRow("转动惯量 J", self.motor_inertia)
        form2.addRow("本体黏性系数 B", self.motor_viscous)
        form2.addRow("直流母线电压", self.motor_voltage)
        form2.addRow("电流限幅", self.motor_current)
        layout.addWidget(mechanical)
        layout.addStretch()
        for widget in (
            self.motor_r, self.motor_ld, self.motor_lq, self.motor_flux, self.motor_poles,
            self.motor_inertia, self.motor_viscous, self.motor_voltage, self.motor_current,
        ):
            widget.valueChanged.connect(self._form_changed)
        return content

    def _build_pid_form(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 16)
        note = QLabel("参数可在仿真运行时修改，立即作用于下一控制周期。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #71858b; padding: 3px;")
        layout.addWidget(note)
        tabs = QTabWidget()
        self.current_pid = PIDEditor(self.config.control.current, "V")
        self.speed_pid = PIDEditor(self.config.control.speed, "A / V")
        self.position_pid = PIDEditor(self.config.control.position, "rpm / A / V")
        tabs.addTab(self.current_pid, "电流环")
        tabs.addTab(self.speed_pid, "速度环")
        tabs.addTab(self.position_pid, "位置环")
        layout.addWidget(tabs)
        ff_group = QGroupBox("控制器选项")
        ff_layout = QVBoxLayout(ff_group)
        self.ff_current = QCheckBox("电流前馈")
        self.ff_speed = QCheckBox("速度前馈")
        self.ff_position = QCheckBox("位置前馈")
        self.auto_tune = QPushButton("自动整定（接口预留）")
        self.auto_tune.setEnabled(False)
        for widget in (self.ff_current, self.ff_speed, self.ff_position, self.auto_tune):
            ff_layout.addWidget(widget)
        layout.addWidget(ff_group)
        layout.addStretch()
        for editor in (self.current_pid, self.speed_pid, self.position_pid):
            editor.changed.connect(self._form_changed)
        for check in (self.ff_current, self.ff_speed, self.ff_position):
            check.toggled.connect(self._form_changed)
        return content

    def _build_disturbance_form(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 16)
        cogging = QGroupBox("齿槽转矩")
        form = QFormLayout(cogging)
        self.cogging_enabled = QCheckBox("启用齿槽效应")
        self.cogging_amplitude = make_double(0.02, 0, 1000, 5, 0.01, " N·m")
        self.cogging_harmonic = make_int(6, 1, 100)
        self.cogging_phase = make_double(0, -360, 360, 2, 5, "°")
        form.addRow("", self.cogging_enabled)
        form.addRow("幅值", self.cogging_amplitude)
        form.addRow("空间谐波", self.cogging_harmonic)
        form.addRow("相位", self.cogging_phase)
        layout.addWidget(cogging)

        friction = QGroupBox("摩擦模型")
        form2 = QFormLayout(friction)
        self.friction_enabled = QCheckBox("启用 Stribeck 复合摩擦")
        self.static_friction = make_double(0.04, 0, 1000, 5, 0.01, " N·m")
        self.coulomb_friction = make_double(0.025, 0, 1000, 5, 0.01, " N·m")
        self.friction_viscous = make_double(0.0002, 0, 100, 7, 0.0001)
        self.stribeck_velocity = make_double(4.77464829, 0.0001, 1e6, 5, 1.0, " rpm")
        form2.addRow("", self.friction_enabled)
        form2.addRow("最大静摩擦", self.static_friction)
        form2.addRow("库仑摩擦", self.coulomb_friction)
        form2.addRow("黏性摩擦系数", self.friction_viscous)
        form2.addRow("Stribeck 速度", self.stribeck_velocity)
        layout.addWidget(friction)

        load = QGroupBox("组合负载转矩")
        form3 = QFormLayout(load)
        self.load_enabled = QCheckBox("启用负载干扰")
        self.load_constant = make_double(0, -1000, 1000, 5, 0.01, " N·m")
        self.load_step = make_double(0.08, -1000, 1000, 5, 0.01, " N·m")
        self.load_step_time = make_double(1.5, 0, 1e4, 4, 0.1, " s")
        self.load_sine_amp = make_double(0, 0, 1000, 5, 0.01, " N·m")
        self.load_sine_freq = make_double(1, 0, 1e4, 4, 0.1, " Hz")
        self.load_noise = make_double(0, 0, 1000, 6, 0.001, " N·m")
        form3.addRow("", self.load_enabled)
        form3.addRow("恒定分量", self.load_constant)
        form3.addRow("阶跃分量", self.load_step)
        form3.addRow("阶跃时刻", self.load_step_time)
        form3.addRow("正弦幅值", self.load_sine_amp)
        form3.addRow("正弦频率", self.load_sine_freq)
        form3.addRow("随机噪声 σ", self.load_noise)
        layout.addWidget(load)

        encoder = QGroupBox("编码器与惯量变化")
        form4 = QFormLayout(encoder)
        self.encoder_noise = make_double(0, 0, 1000, 8, 0.00001, " rad")
        self.encoder_resolution = make_int(65536, 0, 100000000, " cnt/rev")
        self.encoder_delay = make_double(0, 0, 10, 6, 0.0001, " s")
        self.extra_inertia_enabled = QCheckBox("启用负载惯量阶跃")
        self.extra_inertia = make_double(0, 0, 100, 8, 0.0001, " kg·m²")
        self.inertia_time = make_double(1, 0, 1e4, 4, 0.1, " s")
        form4.addRow("位置噪声 σ", self.encoder_noise)
        form4.addRow("分辨率", self.encoder_resolution)
        form4.addRow("采样延迟", self.encoder_delay)
        form4.addRow("", self.extra_inertia_enabled)
        form4.addRow("附加惯量", self.extra_inertia)
        form4.addRow("变化时刻", self.inertia_time)
        layout.addWidget(encoder)
        layout.addStretch()

        for check in (self.cogging_enabled, self.friction_enabled, self.load_enabled, self.extra_inertia_enabled):
            check.toggled.connect(self._form_changed)
        for widget in (
            self.cogging_amplitude, self.cogging_harmonic, self.cogging_phase,
            self.static_friction, self.coulomb_friction, self.friction_viscous,
            self.stribeck_velocity, self.load_constant, self.load_step, self.load_step_time,
            self.load_sine_amp, self.load_sine_freq, self.load_noise, self.encoder_noise,
            self.encoder_resolution, self.encoder_delay, self.extra_inertia, self.inertia_time,
        ):
            widget.valueChanged.connect(self._form_changed)
        return content

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 10, 4, 4)
        self.topology = TopologyWidget()
        self.plots = PlotDashboard()
        layout.addWidget(self.topology)
        layout.addWidget(self.plots, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 10, 10, 8)
        header = QHBoxLayout()
        label = QLabel("实时状态")
        label.setObjectName("SectionTitle")
        self.run_state = QLabel("● STOPPED")
        self.run_state.setObjectName("StatusStopped")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(self.run_state)
        layout.addLayout(header)
        self.time_card = ValueCard("SIM TIME", "s", PLOT_COLORS["muted"])
        self.position_card = ValueCard("POSITION", "rad", PLOT_COLORS["feedback"])
        self.speed_card = ValueCard("SPEED", "rpm", PLOT_COLORS["secondary"])
        self.current_card = ValueCard("Q CURRENT", "A", PLOT_COLORS["reference"])
        self.torque_card = ValueCard("TORQUE", "N·m", PLOT_COLORS["disturbance"])
        for card in (self.time_card, self.position_card, self.speed_card, self.current_card, self.torque_card):
            layout.addWidget(card)

        metric_group = QGroupBox("本次实验指标")
        metric_form = QFormLayout(metric_group)
        self.metric_peak = QLabel("—")
        self.metric_rms = QLabel("—")
        self.metric_settle = QLabel("—")
        self.metric_samples = QLabel("0")
        self.metric_peak_title = QLabel("位置峰值")
        self.metric_rms_title = QLabel("位置误差 RMS")
        metric_form.addRow(self.metric_peak_title, self.metric_peak)
        metric_form.addRow(self.metric_rms_title, self.metric_rms)
        metric_form.addRow("估计调节时间", self.metric_settle)
        metric_form.addRow("记录点数", self.metric_samples)
        layout.addWidget(metric_group)
        self.clear_compare_button = QPushButton("清除对比曲线")
        self.clear_compare_button.clicked.connect(self.clear_comparisons)
        layout.addWidget(self.clear_compare_button)
        layout.addStretch()
        return panel

    def _build_bottom_panel(self) -> QWidget:
        tabs = QTabWidget()
        self.bottom_tabs = tabs
        tabs.setMinimumHeight(145)
        tabs.setMaximumHeight(340)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        tabs.addTab(self.log_view, "运行日志")

        custom_widget = QWidget()
        custom_layout = QHBoxLayout(custom_widget)
        custom_layout.setContentsMargins(14, 12, 14, 12)
        custom_layout.setSpacing(18)

        summary = QVBoxLayout()
        summary.setSpacing(3)
        title = QLabel("独立编辑器")
        title.setObjectName("CustomEditorTitle")
        description = QLabel("在可自由缩放的单独窗口中编写、编译并启用 Python 控制策略。")
        description.setObjectName("CustomEditorDescription")
        self.custom_summary_status = QLabel()
        summary.addWidget(title)
        summary.addWidget(description)
        summary.addWidget(self.custom_summary_status)
        custom_layout.addLayout(summary, 1)

        self.open_custom_editor_button = QPushButton("打开控制器编辑器  ↗")
        self.open_custom_editor_button.setObjectName("PrimaryButton")
        self.open_custom_editor_button.setMinimumWidth(190)
        custom_layout.addWidget(self.open_custom_editor_button, 0, Qt.AlignVCenter)
        tabs.addTab(custom_widget, "自定义控制器")

        self._custom_code_path: Path | None = None
        self._custom_code_needs_compile = False
        self.custom_dialog = self._build_custom_controller_dialog()
        self.open_custom_editor_button.clicked.connect(self.open_custom_controller_editor)
        self._refresh_custom_file_label()
        self._refresh_custom_controller_status()
        return tabs

    def _build_custom_controller_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("CustomControllerDialog")
        dialog.setWindowTitle("自定义控制器 · ServoLab")
        dialog.setModal(False)
        dialog.resize(1080, 720)
        dialog.setMinimumSize(760, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(1)
        eyebrow = QLabel("CUSTOM CONTROL / PYTHON")
        eyebrow.setObjectName("SectionTitle")
        title = QLabel("控制器代码编辑器")
        title.setObjectName("DialogTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header.addLayout(heading)
        header.addStretch()
        warning = QLabel("独立进程  ·  40 ms 超时  ·  仅运行可信代码")
        warning.setObjectName("CustomEditorWarning")
        header.addWidget(warning, 0, Qt.AlignBottom)
        layout.addLayout(header)

        editor_frame = QFrame()
        editor_frame.setObjectName("CodeEditorFrame")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(1, 1, 1, 1)
        editor_layout.setSpacing(0)
        editor_bar = QFrame()
        editor_bar.setObjectName("CodeEditorBar")
        editor_bar_layout = QHBoxLayout(editor_bar)
        editor_bar_layout.setContentsMargins(11, 7, 11, 7)
        self.custom_file_label = QLabel()
        self.custom_file_label.setObjectName("CodeFileName")
        self.open_custom_code_button = QPushButton("打开代码")
        self.save_custom_code_button = QPushButton("保存代码")
        editor_bar_layout.addWidget(self.custom_file_label)
        editor_bar_layout.addStretch()
        editor_bar_layout.addWidget(self.open_custom_code_button)
        editor_bar_layout.addWidget(self.save_custom_code_button)
        editor_layout.addWidget(editor_bar)

        generator_bar = QFrame()
        generator_bar.setObjectName("ControllerGeneratorBar")
        generator_layout = QVBoxLayout(generator_bar)
        generator_layout.setContentsMargins(11, 8, 11, 9)
        generator_layout.setSpacing(6)
        generator_header = QHBoxLayout()
        generator_title = QLabel("AUTO SYNTHESIS")
        generator_title.setObjectName("GeneratorTitle")
        self.custom_generator_context = QLabel()
        self.custom_generator_context.setObjectName("GeneratorContext")
        self.generate_custom_code_button = QPushButton("按当前配置生成")
        self.generate_custom_code_button.setObjectName("GenerateButton")
        generator_header.addWidget(generator_title)
        generator_header.addSpacing(8)
        generator_header.addWidget(self.custom_generator_context)
        generator_header.addStretch()
        generator_header.addWidget(self.generate_custom_code_button)
        generator_layout.addLayout(generator_header)

        generator_options = QHBoxLayout()
        generator_options.setSpacing(18)
        option_label = QLabel("生成选项")
        option_label.setObjectName("CodeShortcut")
        self.generator_feedforward = QCheckBox("参考前馈 Kff")
        self.generator_back_emf = QCheckBox("反电动势补偿")
        self.generator_decoupling = QCheckBox("dq 解耦")
        self.generator_friction = QCheckBox("黏性摩擦补偿")
        self.generator_anti_windup = QCheckBox("抗积分饱和")
        self.generator_back_emf.setChecked(True)
        self.generator_decoupling.setChecked(True)
        self.generator_anti_windup.setChecked(True)
        generator_options.addWidget(option_label)
        for checkbox in (
            self.generator_feedforward,
            self.generator_back_emf,
            self.generator_decoupling,
            self.generator_friction,
            self.generator_anti_windup,
        ):
            generator_options.addWidget(checkbox)
        generator_options.addStretch()
        generator_layout.addLayout(generator_options)
        editor_layout.addWidget(generator_bar)

        initial_code = generate_custom_controller_code(
            self.config.control.mode,
            self.config.command.reference_type,
            self.config.control,
            self.config.motor,
            self._controller_generation_options(),
        )
        self.code_editor = QPlainTextEdit(initial_code)
        self.code_editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code_editor.setObjectName("CustomCodeEditor")
        self.code_editor.setStyleSheet(
            'font-family: "SF Mono", "Cascadia Code", "JetBrains Mono", monospace; '
            "font-size: 13px; padding: 12px;"
        )
        PythonHighlighter(self.code_editor.document())
        self.code_editor.document().setModified(False)
        editor_layout.addWidget(self.code_editor, 1)
        layout.addWidget(editor_frame, 1)

        footer = QHBoxLayout()
        footer.setSpacing(9)
        self.custom_dialog_status = QLabel()
        footer.addWidget(self.custom_dialog_status)
        footer.addStretch()
        api_button = QPushButton("状态 API")
        self.enable_custom = QCheckBox("接管控制输出")
        self.enable_custom.setEnabled(False)
        self.stop_custom_button = QPushButton("停止控制器")
        self.stop_custom_button.setObjectName("DangerButton")
        self.compile_custom_button = QPushButton("编译并启动")
        self.compile_custom_button.setObjectName("PrimaryButton")
        self.compile_custom_button.setMinimumWidth(140)
        footer.addWidget(api_button)
        footer.addWidget(self.enable_custom)
        footer.addWidget(self.stop_custom_button)
        footer.addWidget(self.compile_custom_button)
        layout.addLayout(footer)

        self.compile_custom_button.clicked.connect(self.compile_custom_controller)
        self.stop_custom_button.clicked.connect(self.stop_custom_controller)
        self.enable_custom.toggled.connect(self._toggle_custom_controller)
        api_button.clicked.connect(self.show_custom_api)
        self.generate_custom_code_button.clicked.connect(self.generate_custom_controller_from_configuration)
        self.open_custom_code_button.clicked.connect(self.open_custom_controller_code)
        self.save_custom_code_button.clicked.connect(self.save_custom_controller_code)
        self.code_editor.document().modificationChanged.connect(self._mark_custom_controller_dirty)

        compile_action = QAction(dialog)
        compile_action.setShortcut(QKeySequence("Ctrl+Return"))
        compile_action.triggered.connect(self.compile_custom_controller)
        dialog.addAction(compile_action)
        save_action = QAction(dialog)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_custom_controller_code)
        dialog.addAction(save_action)
        return dialog

    def open_custom_controller_editor(self) -> None:
        self._refresh_custom_controller_generator_context()
        self.custom_dialog.show()
        self.custom_dialog.raise_()
        self.custom_dialog.activateWindow()
        self.code_editor.setFocus()

    def generate_custom_controller_from_configuration(self) -> None:
        if not self._confirm_replace_custom_controller_code():
            return
        self._sync_config_from_form()
        code = generate_custom_controller_code(
            self.config.control.mode,
            self.config.command.reference_type,
            self.config.control,
            self.config.motor,
            self._controller_generation_options(),
        )
        self.code_editor.setPlainText(code)
        self._custom_code_path = None
        self._custom_code_needs_compile = True
        self.code_editor.document().setModified(True)
        self._refresh_custom_file_label()
        self._refresh_custom_controller_status()
        self.code_editor.setFocus()
        self._refresh_custom_controller_generator_context()
        self._log(
            f"已根据 {self.config.control.mode.value} / "
            f"{self.config.command.reference_type.value} 生成自定义控制器。"
        )

    def _controller_generation_options(self) -> ControllerGenerationOptions:
        return ControllerGenerationOptions(
            reference_feedforward=self.generator_feedforward.isChecked(),
            back_emf_compensation=self.generator_back_emf.isChecked(),
            dq_decoupling=self.generator_decoupling.isChecked(),
            friction_compensation=self.generator_friction.isChecked(),
            anti_windup=self.generator_anti_windup.isChecked(),
        )

    def _refresh_custom_controller_generator_context(self) -> None:
        if not hasattr(self, "custom_generator_context"):
            return
        mode = self.config.control.mode.value
        target = self.config.command.reference_type.value
        self.custom_generator_context.setText(f"{mode}  →  {target}")
        self.custom_generator_context.setToolTip("参数取自主界面当前 PID 与电机配置")

    def open_custom_controller_code(self) -> None:
        if not self._confirm_replace_custom_controller_code():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开自定义控制器代码",
            "",
            "Python 代码 (*.py);;所有文件 (*)",
        )
        if not path:
            return
        try:
            code = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(self, "代码打开失败", str(exc))
            return
        self.code_editor.setPlainText(code)
        self._custom_code_path = Path(path)
        self._custom_code_needs_compile = True
        self.code_editor.document().setModified(False)
        self._refresh_custom_file_label()
        self._refresh_custom_controller_status()
        self.code_editor.setFocus()
        self._log(f"已打开自定义控制器代码：{path}")

    def save_custom_controller_code(self) -> bool:
        path = self._custom_code_path
        if path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "保存自定义控制器代码",
                "custom_controller.py",
                "Python 代码 (*.py)",
            )
            if not selected:
                return False
            path = Path(selected)
            if not path.suffix:
                path = path.with_suffix(".py")
        try:
            path.write_text(self.code_editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "代码保存失败", str(exc))
            return False
        self._custom_code_path = path
        self.code_editor.document().setModified(False)
        self._refresh_custom_file_label()
        self._log(f"自定义控制器代码已保存：{path}")
        return True

    def _confirm_replace_custom_controller_code(self) -> bool:
        if not self.code_editor.document().isModified():
            return True
        choice = QMessageBox.warning(
            self,
            "代码尚未保存",
            "当前代码有未保存的修改，是否先保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Save:
            return self.save_custom_controller_code()
        return choice == QMessageBox.Discard

    def _refresh_custom_file_label(self) -> None:
        name = self._custom_code_path.name if self._custom_code_path else "controller.py"
        unsaved = "  • 未保存" if self.code_editor.document().isModified() else ""
        self.custom_file_label.setText(f"●  {name}{unsaved}")
        self.custom_file_label.setToolTip(
            str(self._custom_code_path) if self._custom_code_path else "尚未保存为文件"
        )

    def _connect_shortcuts(self) -> None:
        run_action = QAction(self)
        run_action.setShortcut(QKeySequence(Qt.Key_Space))
        run_action.triggered.connect(lambda: self.pause_simulation() if self.running else self.start_simulation())
        self.addAction(run_action)
        reset_action = QAction(self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(self.reset_simulation)
        self.addAction(reset_action)

    def _form_changed(self, *_args) -> None:
        if self._updating_form:
            return
        old_mode = self.config.control.mode
        old_reference_type = self.config.command.reference_type
        selected_mode = LoopMode(self.mode_combo.currentText())
        if selected_mode != old_mode:
            self._set_reference_options(selected_mode, old_reference_type)
        self._sync_config_from_form()
        self.topology.set_mode(self.config.control.mode)
        self.topology.set_reference_type(self.config.command.reference_type)
        if old_mode != self.config.control.mode:
            self.controller_reset_for_mode()
            self._log(f"控制拓扑切换为：{self.config.control.mode.value}")
        if old_reference_type != self.config.command.reference_type:
            self.controller_reset_for_mode()
            self._log(f"用户输入切换为：{self.config.command.reference_type.value}")
        self._update_command_units()
        self._update_reference_display()
        self._update_manual_drag_line()
        self._refresh_custom_controller_generator_context()

    def _sync_config_from_form(self) -> None:
        cfg = self.config
        cfg.name = self.experiment_name.text().strip() or "未命名实验"
        cfg.control.mode = LoopMode(self.mode_combo.currentText())
        cfg.command.reference_type = ReferenceType(self.reference_combo.currentText())
        cfg.command.kind = CommandType(self.command_combo.currentText())
        cfg.command.amplitude = self.command_amplitude.value()
        cfg.command.offset = self.command_offset.value()
        cfg.command.frequency = self.command_frequency.value()
        cfg.command.start_time = self.command_start.value()
        cfg.command.rise_time = self.command_rise.value()
        cfg.command.hold_time = self.command_hold.value()
        cfg.command.manual_value = self.command_manual.value()
        cfg.simulation.dt = self.sim_dt.value()
        cfg.simulation.duration = self.sim_duration.value()
        cfg.simulation.plot_interval = max(self.plot_interval.value(), cfg.simulation.dt)
        cfg.simulation.realtime_factor = self.realtime_factor.value()

        cfg.motor.resistance = self.motor_r.value()
        cfg.motor.ld = self.motor_ld.value()
        cfg.motor.lq = self.motor_lq.value()
        cfg.motor.flux = self.motor_flux.value()
        cfg.motor.pole_pairs = self.motor_poles.value()
        cfg.motor.inertia = self.motor_inertia.value()
        cfg.motor.viscous = self.motor_viscous.value()
        cfg.motor.dc_voltage = self.motor_voltage.value()
        cfg.motor.current_limit = self.motor_current.value()

        self.current_pid.update_config(cfg.control.current)
        self.speed_pid.update_config(cfg.control.speed)
        self.position_pid.update_config(cfg.control.position)
        cfg.control.current_feedforward = self.ff_current.isChecked()
        cfg.control.speed_feedforward = self.ff_speed.isChecked()
        cfg.control.position_feedforward = self.ff_position.isChecked()

        d = cfg.disturbance
        d.cogging_enabled = self.cogging_enabled.isChecked()
        d.cogging_amplitude = self.cogging_amplitude.value()
        d.cogging_harmonic = self.cogging_harmonic.value()
        d.cogging_phase_deg = self.cogging_phase.value()
        d.friction_enabled = self.friction_enabled.isChecked()
        d.static_friction = self.static_friction.value()
        d.coulomb_friction = self.coulomb_friction.value()
        d.viscous_friction = self.friction_viscous.value()
        d.stribeck_velocity = self.stribeck_velocity.value()
        d.load_enabled = self.load_enabled.isChecked()
        d.load_constant = self.load_constant.value()
        d.load_step = self.load_step.value()
        d.load_step_time = self.load_step_time.value()
        d.load_sine_amplitude = self.load_sine_amp.value()
        d.load_sine_frequency = self.load_sine_freq.value()
        d.load_noise_std = self.load_noise.value()
        d.encoder_noise_std = self.encoder_noise.value()
        d.encoder_resolution = self.encoder_resolution.value()
        d.encoder_delay = self.encoder_delay.value()
        d.extra_inertia_enabled = self.extra_inertia_enabled.isChecked()
        d.extra_inertia = self.extra_inertia.value()
        d.inertia_step_time = self.inertia_time.value()

        # Keep long-lived runtime objects in sync with mutable parameters.
        self.simulation.disturbance.dt = cfg.simulation.dt
        self.sample_status.setText(
            f"dt {cfg.simulation.dt * 1e6:.0f} μs  ·  plot {cfg.simulation.plot_interval * 1e3:.1f} ms"
        )

    def _load_form_from_config(self) -> None:
        self._updating_form = True
        cfg = self.config
        self.experiment_name.setText(cfg.name)
        self.mode_combo.setCurrentText(cfg.control.mode.value)
        self._set_reference_options(cfg.control.mode, cfg.command.reference_type)
        self.command_combo.setCurrentText(cfg.command.kind.value)
        fields = (
            (self.command_amplitude, cfg.command.amplitude), (self.command_offset, cfg.command.offset),
            (self.command_frequency, cfg.command.frequency), (self.command_start, cfg.command.start_time),
            (self.command_rise, cfg.command.rise_time), (self.command_hold, cfg.command.hold_time),
            (self.command_manual, cfg.command.manual_value), (self.sim_dt, cfg.simulation.dt),
            (self.sim_duration, cfg.simulation.duration), (self.plot_interval, cfg.simulation.plot_interval),
            (self.realtime_factor, cfg.simulation.realtime_factor), (self.motor_r, cfg.motor.resistance),
            (self.motor_ld, cfg.motor.ld), (self.motor_lq, cfg.motor.lq),
            (self.motor_flux, cfg.motor.flux), (self.motor_poles, cfg.motor.pole_pairs),
            (self.motor_inertia, cfg.motor.inertia), (self.motor_viscous, cfg.motor.viscous),
            (self.motor_voltage, cfg.motor.dc_voltage), (self.motor_current, cfg.motor.current_limit),
        )
        for widget, value in fields:
            widget.setValue(value)
        self.current_pid.load_config(cfg.control.current)
        self.speed_pid.load_config(cfg.control.speed)
        self.position_pid.load_config(cfg.control.position)
        self.ff_current.setChecked(cfg.control.current_feedforward)
        self.ff_speed.setChecked(cfg.control.speed_feedforward)
        self.ff_position.setChecked(cfg.control.position_feedforward)
        d = cfg.disturbance
        checks = (
            (self.cogging_enabled, d.cogging_enabled), (self.friction_enabled, d.friction_enabled),
            (self.load_enabled, d.load_enabled), (self.extra_inertia_enabled, d.extra_inertia_enabled),
        )
        for widget, checked in checks:
            widget.setChecked(checked)
        d_fields = (
            (self.cogging_amplitude, d.cogging_amplitude), (self.cogging_harmonic, d.cogging_harmonic),
            (self.cogging_phase, d.cogging_phase_deg), (self.static_friction, d.static_friction),
            (self.coulomb_friction, d.coulomb_friction), (self.friction_viscous, d.viscous_friction),
            (self.stribeck_velocity, d.stribeck_velocity), (self.load_constant, d.load_constant),
            (self.load_step, d.load_step), (self.load_step_time, d.load_step_time),
            (self.load_sine_amp, d.load_sine_amplitude), (self.load_sine_freq, d.load_sine_frequency),
            (self.load_noise, d.load_noise_std), (self.encoder_noise, d.encoder_noise_std),
            (self.encoder_resolution, d.encoder_resolution), (self.encoder_delay, d.encoder_delay),
            (self.extra_inertia, d.extra_inertia), (self.inertia_time, d.inertia_step_time),
        )
        for widget, value in d_fields:
            widget.setValue(value)
        self.topology.set_mode(cfg.control.mode)
        self.topology.set_reference_type(cfg.command.reference_type)
        self._updating_form = False
        self._sync_config_from_form()
        self._update_command_units()
        self._update_reference_display()
        self._update_manual_drag_line()
        self._refresh_custom_controller_generator_context()

    def _set_reference_options(
        self,
        mode: LoopMode,
        preferred: ReferenceType | None = None,
    ) -> None:
        allowed = allowed_reference_types(mode)
        selected = preferred if preferred in allowed else default_reference_type(mode)
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItems([item.value for item in allowed])
        self.reference_combo.setCurrentText(selected.value)
        self.reference_combo.blockSignals(False)

    def _update_command_units(self) -> None:
        reference_type = self.config.command.reference_type
        if reference_type == ReferenceType.CURRENT:
            unit = " A"
        elif reference_type == ReferenceType.SPEED:
            unit = " rpm"
        else:
            unit = " rad"
        for field in (self.command_amplitude, self.command_offset, self.command_manual):
            field.setSuffix(unit)

    def _update_reference_display(self) -> None:
        self.plots.set_input_reference(
            self.config.command.reference_type,
            has_position_outer_loop(self.config.control.mode),
        )

    def _update_manual_drag_line(self) -> None:
        self.plots.set_manual_control(
            self.config.command.kind == CommandType.MANUAL,
            self.config.command.reference_type,
            self.config.command.manual_value,
            self._manual_line_changed,
        )

    def _manual_line_changed(self, value: float) -> None:
        self.command_manual.setValue(value)

    def controller_reset_for_mode(self) -> None:
        self.simulation.controller.reset()

    def start_simulation(self) -> None:
        self._sync_config_from_form()
        if self.simulation.time >= self.config.simulation.duration:
            self.simulation.reset()
        self.running = True
        self._last_wall_time = time.perf_counter()
        self.run_state.setText("● RUNNING")
        self.run_state.setObjectName("StatusRunning")
        self.run_state.style().unpolish(self.run_state)
        self.run_state.style().polish(self.run_state)
        self.status_message.setText("RUNNING")
        self.status_message.setObjectName("StatusRunning")
        self._log("实时仿真开始。")

    def pause_simulation(self) -> None:
        if self.running:
            self._log(f"仿真暂停于 t = {self.simulation.time:.4f} s。")
        self.running = False
        self.run_state.setText("● PAUSED")
        self.run_state.setObjectName("StatusPaused")
        self.run_state.style().unpolish(self.run_state)
        self.run_state.style().polish(self.run_state)
        self.status_message.setText("PAUSED")
        self.status_message.setObjectName("StatusPaused")

    def reset_simulation(self) -> None:
        self.running = False
        self._sync_config_from_form()
        self.simulation.reset()
        self.run_state.setText("● STOPPED")
        self.run_state.setObjectName("StatusStopped")
        self.status_message.setText("READY")
        self._refresh_ui()
        self._log("仿真状态与曲线已复位。")

    def single_step(self) -> None:
        self.pause_simulation()
        self._sync_config_from_form()
        try:
            self.simulation.step()
        except CustomControllerError as exc:
            self._handle_custom_error(exc)
        self._refresh_ui()

    def _simulation_tick(self) -> None:
        if not self.running:
            return
        now = time.perf_counter()
        elapsed = min(now - self._last_wall_time, 0.1)
        self._last_wall_time = now
        dt = self.config.simulation.dt
        steps = max(1, int(elapsed * self.config.simulation.realtime_factor / max(dt, 1e-9)))
        try:
            self.simulation.step(steps)
        except CustomControllerError as exc:
            self._handle_custom_error(exc)
            return
        if self.simulation.time >= self.config.simulation.duration:
            self.pause_simulation()
            self._log("已到达设定实验时长。")
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        sample = self.simulation.last_sample
        if sample:
            self.time_card.set_value(sample.get("time", 0.0), 4)
            self.position_card.set_value(sample.get("position", 0.0), 4)
            self.speed_card.set_value(sample.get("speed", 0.0), 3)
            self.current_card.set_value(sample.get("iq", 0.0), 3)
            self.torque_card.set_value(sample.get("torque", 0.0), 4)
        history = self.simulation.history.data
        self.plots.update_data(history)
        self.metric_samples.setText(str(len(self.simulation.history)))
        self._update_metrics(history)

    def _update_metrics(self, history: dict[str, list[float]]) -> None:
        times = history.get("time", [])
        reference_type = self.config.command.reference_type
        if reference_type == ReferenceType.SPEED:
            title = "速度"
            unit = "rpm"
            feedback = history.get("speed", [])
            target = history.get("user_speed_ref", [])
        elif reference_type == ReferenceType.CURRENT:
            title = "电流"
            unit = "A"
            feedback = history.get("iq", [])
            target = history.get("current_ref", [])
        else:
            title = "位置"
            unit = "rad"
            feedback = history.get("position", [])
            target = history.get("position_ref", [])
        if not feedback:
            return
        error = [ref - actual for ref, actual in zip(target, feedback)]
        self.metric_peak_title.setText(f"{title}峰值")
        self.metric_rms_title.setText(f"{title}误差 RMS")
        self.metric_peak.setText(f"{max(abs(v) for v in feedback):.4f} {unit}")
        if error:
            rms = math.sqrt(sum(v * v for v in error) / len(error))
            self.metric_rms.setText(f"{rms:.5f} {unit}")
        settling = self._settling_time(times, target, feedback)
        self.metric_settle.setText("—" if settling is None else f"{settling:.3f} s")

    @staticmethod
    def _settling_time(times: list[float], reference: list[float], feedback: list[float]) -> float | None:
        if len(times) < 5 or not reference:
            return None
        final = reference[-1]
        tolerance = max(abs(final) * 0.02, 1e-3)
        for index in range(len(times)):
            if all(abs(reference[j] - feedback[j]) <= tolerance for j in range(index, len(times))):
                return times[index]
        return None

    def run_offline(self) -> None:
        self.pause_simulation()
        self._sync_config_from_form()
        progress = QProgressDialog("正在执行离线仿真…", "取消", 0, 100, self)
        progress.setWindowTitle("离线高速仿真")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(250)
        started = time.perf_counter()

        cancelled = False

        def update_progress(value: float) -> None:
            nonlocal cancelled
            progress.setValue(int(value * 100))
            QApplication.processEvents()
            cancelled = progress.wasCanceled()
            if cancelled:
                raise InterruptedError

        try:
            self.simulation.run_offline(progress=update_progress)
        except InterruptedError:
            self._log("离线仿真已由用户取消。")
        except CustomControllerError as exc:
            self._handle_custom_error(exc)
        else:
            elapsed = time.perf_counter() - started
            self._log(
                f"离线仿真完成：{self.config.simulation.duration:.3f} s 模型时间，"
                f"耗时 {elapsed:.3f} s，记录 {len(self.simulation.history)} 点。"
            )
        finally:
            progress.close()
            self._refresh_ui()

    def keep_comparison(self) -> None:
        if len(self.simulation.history) < 2:
            QMessageBox.information(self, "保留对比", "当前还没有可保留的仿真数据。")
            return
        if len(self.overlays) >= 4:
            self.overlays.pop(0)
        name = f"{self.config.name} #{len(self.overlays) + 1}"
        self.overlays.append((name, self.simulation.history.snapshot()))
        self.plots.set_overlays(self.overlays)
        self._log(f"已保留对比曲线：{name}")

    def clear_comparisons(self) -> None:
        self.overlays.clear()
        self.plots.set_overlays([])
        self._log("对比曲线已清除。")

    def load_trajectory(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "载入轨迹", "", "CSV 轨迹 (*.csv);;所有文件 (*)")
        if not path:
            return
        try:
            times, values = load_trajectory_csv(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "轨迹格式错误", str(exc))
            return
        self.config.command.trajectory_time = times
        self.config.command.trajectory_value = values
        self.command_combo.setCurrentText(CommandType.TRAJECTORY.value)
        self._log(f"已载入轨迹 {Path(path).name}，共 {len(times)} 点。")

    def save_experiment(self) -> None:
        self._sync_config_from_form()
        path, _ = QFileDialog.getSaveFileName(self, "保存实验配置", f"{self.config.name}.json", "实验配置 (*.json)")
        if not path:
            return
        try:
            self.config.save(path)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._log(f"实验配置已保存：{path}")

    def load_experiment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开实验配置", "", "实验配置 (*.json)")
        if not path:
            return
        try:
            config = ExperimentConfig.load(path)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "配置读取失败", str(exc))
            return
        self.pause_simulation()
        self.config = config
        self.simulation.apply_config(config)
        self.simulation.custom_controller = self.custom_process
        self._load_form_from_config()
        self._refresh_ui()
        self._log(f"已打开实验配置：{path}")

    def export_data_menu(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("导出实验结果")
        layout = QVBoxLayout(dialog)
        label = QLabel("选择导出格式")
        label.setObjectName("SectionTitle")
        csv_button = QPushButton("导出全部通道为 CSV")
        png_button = QPushButton("导出当前曲线为 PNG")
        layout.addWidget(label)
        layout.addWidget(csv_button)
        layout.addWidget(png_button)
        csv_button.clicked.connect(lambda: (dialog.accept(), self.export_csv()))
        png_button.clicked.connect(lambda: (dialog.accept(), self.export_plot()))
        dialog.exec_()

    def export_csv(self) -> None:
        if len(self.simulation.history) < 2:
            QMessageBox.information(self, "导出数据", "当前没有足够的仿真数据。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出数据", f"{self.config.name}.csv", "CSV 数据 (*.csv)")
        if path:
            try:
                self.simulation.history.export_csv(path)
                self._log(f"数据已导出：{path}")
            except OSError as exc:
                QMessageBox.critical(self, "导出失败", str(exc))

    def export_plot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出当前曲线", f"{self.config.name}.png", "PNG 图片 (*.png)")
        if not path:
            return
        try:
            exporter = ImageExporter(self.plots.current_plot().plotItem)
            exporter.parameters()["width"] = 1800
            exporter.export(path)
            self._log(f"曲线图片已导出：{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def compile_custom_controller(self) -> None:
        try:
            self.custom_process.start(self.code_editor.toPlainText())
        except CustomControllerError as exc:
            self.enable_custom.setChecked(False)
            self.enable_custom.setEnabled(False)
            self.simulation.use_custom_controller = False
            self._set_custom_controller_status("error")
            QMessageBox.critical(self, "自定义控制器编译失败", str(exc))
            self._log(f"自定义控制器错误：{exc}")
            return
        self._custom_code_needs_compile = False
        self.enable_custom.setEnabled(True)
        self.enable_custom.setChecked(True)
        self._refresh_custom_controller_status()
        self._log("自定义控制器编译成功并已接管控制输出。")

    def stop_custom_controller(self) -> None:
        self.enable_custom.setChecked(False)
        self.enable_custom.setEnabled(False)
        self.custom_process.stop()
        self._refresh_custom_controller_status()
        self._log("自定义控制器进程已停止，恢复内置控制器。")

    def _toggle_custom_controller(self, enabled: bool) -> None:
        self.simulation.use_custom_controller = enabled and self.custom_process.running
        self._refresh_custom_controller_status()
        if self.simulation.use_custom_controller:
            self._log("控制输出已切换到自定义控制器。")

    def _mark_custom_controller_dirty(self, modified: bool) -> None:
        if modified:
            self._custom_code_needs_compile = True
        self._refresh_custom_file_label()
        self._refresh_custom_controller_status()

    def _refresh_custom_controller_status(self) -> None:
        if self._custom_code_needs_compile:
            state = "modified_running" if self.custom_process.running else "modified"
        elif self.custom_process.running:
            state = "active" if self.simulation.use_custom_controller else "ready"
        else:
            state = "idle"
        self._set_custom_controller_status(state)

    def _set_custom_controller_status(self, state: str) -> None:
        states = {
            "idle": ("●  NOT RUNNING", "等待编译", "#73868c"),
            "modified": ("●  EDITED", "代码已修改，等待编译", "#e3b45d"),
            "modified_running": (
                "●  EDITED / PROCESS RUNNING",
                "当前进程仍使用上次编译的代码",
                "#e3b45d",
            ),
            "ready": ("●  PROCESS READY", "已编译，尚未接管控制输出", "#6fbee8"),
            "active": ("●  OUTPUT ACTIVE", "自定义控制器正在接管输出", "#45e1b4"),
            "error": ("●  COMPILE ERROR", "编译失败，请修改代码后重试", "#ef756f"),
        }
        status, summary, color = states[state]
        self.custom_dialog_status.setText(status)
        self.custom_dialog_status.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.custom_summary_status.setText(summary)
        self.custom_summary_status.setStyleSheet(f"color: {color};")

    def _handle_custom_error(self, error: Exception) -> None:
        self.pause_simulation()
        self.simulation.use_custom_controller = False
        self.enable_custom.blockSignals(True)
        self.enable_custom.setChecked(False)
        self.enable_custom.blockSignals(False)
        self.enable_custom.setEnabled(False)
        self.custom_process.stop()
        self._set_custom_controller_status("error")
        self._log(f"自定义控制器已停止：{error}")
        QMessageBox.critical(self, "自定义控制器运行错误", str(error))

    def show_custom_api(self) -> None:
        QMessageBox.information(
            self,
            "自定义控制器 API",
            "state：id, iq, theta, omega (rpm), torque, t\n"
            "reference：command, user_input, position, speed (rpm), current\n"
            "params：跨控制周期保留的字典\n"
            "dt：控制周期，单位 s\n\n"
            "返回 {\"vd\": ..., \"vq\": ...}，或仅返回 vq 数值。\n"
            "math 模块已预载；不允许 import。",
        )

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}]  {message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.custom_process.stop()
        event.accept()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ServoLab")
    app.setOrganizationName("ServoLab")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    font = QFont()
    font.setFamilies(["DIN Alternate", "PingFang SC", "Microsoft YaHei UI", "Noto Sans CJK SC"])
    app.setFont(font)
    window = ServoLabWindow()
    window.show()
    return app.exec_()
