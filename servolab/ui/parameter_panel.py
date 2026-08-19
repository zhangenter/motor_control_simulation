from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    CommandType,
    CurrentAxis,
    ExperimentConfig,
    LoopMode,
    ReferenceType,
    allowed_reference_types,
    default_reference_type,
)
from .current_test_editor import CurrentTestEditor
from .disturbance_editor import DisturbanceEditor
from .feedback_editor import FeedbackEditor
from .widgets import PIDEditor, make_double, make_int


class ParameterPanel(QFrame):
    changed = pyqtSignal()
    trajectory_requested = pyqtSignal()

    def __init__(self, config: ExperimentConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._loading = False
        self.setMinimumWidth(300)
        self.setMaximumWidth(400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 8, 8)
        title = QLabel("实验参数")
        title.setObjectName("SectionTitle")
        outer.addWidget(title)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { padding-left: 9px; padding-right: 9px; }")
        self.tabs.addTab(self._scroll_tab(self._build_experiment_form()), "实验")
        self.tabs.addTab(self._scroll_tab(self._build_motor_form()), "电机")
        self.tabs.addTab(self._scroll_tab(self._build_pid_form()), "PID")
        self.feedback_editor = FeedbackEditor(self.config.feedback)
        self.feedback_editor.changed.connect(self._field_changed)
        self.tabs.addTab(self._scroll_tab(self.feedback_editor), "反馈")
        self.tabs.addTab(self._scroll_tab(self._build_disturbance_form()), "干扰")
        outer.addWidget(self.tabs)

    @staticmethod
    def _scroll_tab(content: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(content)
        return area

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

        self.current_test = CurrentTestEditor()
        self.axis_d = self.current_test.axis_d
        self.axis_q = self.current_test.axis_q
        self.lock_rotor = self.current_test.lock_rotor
        layout.addWidget(self.current_test)

        self.command_group = QGroupBox("指令发生器")
        command_form = QFormLayout(self.command_group)
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
        fields = (
            ("波形", self.command_combo),
            ("幅值", self.command_amplitude),
            ("偏置", self.command_offset),
            ("频率", self.command_frequency),
            ("起始时刻", self.command_start),
            ("上升时间", self.command_rise),
            ("保持时间", self.command_hold),
            ("手动值", self.command_manual),
        )
        self.command_labels = {}
        for label, widget in fields:
            command_form.addRow(label, widget)
            self.command_labels[widget] = command_form.labelForField(widget)
        command_form.addRow("轨迹文件", self.trajectory_button)
        layout.addWidget(self.command_group)

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
        self._connect_experiment_fields()
        return content

    def _connect_experiment_fields(self) -> None:
        self.mode_combo.currentTextChanged.connect(self._field_changed)
        self.reference_combo.currentTextChanged.connect(self._field_changed)
        self.current_test.changed.connect(self._current_test_changed)
        self.command_combo.currentTextChanged.connect(self._field_changed)
        self.experiment_name.editingFinished.connect(self._field_changed)
        fields = (
            self.command_amplitude,
            self.command_offset,
            self.command_frequency,
            self.command_start,
            self.command_rise,
            self.command_hold,
            self.command_manual,
            self.sim_dt,
            self.sim_duration,
            self.plot_interval,
            self.realtime_factor,
        )
        for widget in fields:
            widget.valueChanged.connect(self._field_changed)
        self.trajectory_button.clicked.connect(self.trajectory_requested)

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
            ("定子电阻 Rs（每相）", self.motor_r),
            ("d 轴电感 Ld（每相等效）", self.motor_ld),
            ("q 轴电感 Lq（每相等效）", self.motor_lq),
            ("永磁磁链 ψf", self.motor_flux),
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
        for label, widget in (
            ("转动惯量 J", self.motor_inertia),
            ("本体黏性系数 B", self.motor_viscous),
            ("直流母线电压", self.motor_voltage),
            ("电流限幅", self.motor_current),
        ):
            form2.addRow(label, widget)
        layout.addWidget(mechanical)
        layout.addStretch()
        for widget in self._motor_fields():
            widget.valueChanged.connect(self._field_changed)
        return content

    def _build_pid_form(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 16)
        note = QLabel("参数可在仿真运行时修改，立即作用于下一控制周期。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #71858b; padding: 3px;")
        layout.addWidget(note)
        self.pid_tabs = QTabWidget()
        self.current_axis_tabs = QTabWidget()
        self.current_d_pid = PIDEditor(self.config.control.current_d, "V")
        self.current_q_pid = PIDEditor(self.config.control.current, "V")
        self.current_axis_tabs.addTab(self.current_d_pid, "d 轴 PI")
        self.current_axis_tabs.addTab(self.current_q_pid, "q 轴 PI")
        self.current_pid = self.current_q_pid
        self.speed_pid = PIDEditor(self.config.control.speed, "A / V")
        self.position_pid = PIDEditor(self.config.control.position, "rpm / A / V")
        self.pid_tabs.addTab(self.current_axis_tabs, "dq 电流环")
        self.pid_tabs.addTab(self.speed_pid, "速度环")
        self.pid_tabs.addTab(self.position_pid, "位置环")
        layout.addWidget(self.pid_tabs)
        ff_group = QGroupBox("控制器选项")
        ff_layout = QVBoxLayout(ff_group)
        self.ff_current = QCheckBox("电流前馈")
        self.ff_speed = QCheckBox("速度前馈")
        self.ff_position = QCheckBox("位置前馈")
        self.auto_tune = QPushButton("PID 计算器")
        self.auto_tune.setEnabled(False)
        for widget in (self.ff_current, self.ff_speed, self.ff_position, self.auto_tune):
            ff_layout.addWidget(widget)
        layout.addWidget(ff_group)
        layout.addStretch()
        for editor in (self.current_d_pid, self.current_q_pid, self.speed_pid, self.position_pid):
            editor.changed.connect(self._field_changed)
        for check in (self.ff_current, self.ff_speed, self.ff_position):
            check.toggled.connect(self._field_changed)
        return content

    def _build_disturbance_form(self) -> QWidget:
        self.disturbance_editor = DisturbanceEditor(self.config.disturbance)
        self.disturbance_tabs = self.disturbance_editor.tabs
        self.disturbance_editor.changed.connect(self._field_changed)
        return self.disturbance_editor

    def _field_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def sync_mode_dependent_controls(self, mode: LoopMode) -> None:
        self.update_current_test_controls(mode, self.current_test.selected_axis())

    def update_config(self, config: ExperimentConfig) -> None:
        self.config = config
        config.name = self.experiment_name.text().strip() or "未命名实验"
        config.control.mode = LoopMode(self.mode_combo.currentText())
        config.command.reference_type = ReferenceType(self.reference_combo.currentText())
        config.command.kind = CommandType(self.command_combo.currentText())
        config.command.current_axis = self.current_test.selected_axis()
        config.command.lock_rotor = self.lock_rotor.isChecked()
        self._update_command_config(config)
        self._update_motor_config(config)
        self._update_control_config(config)
        self.feedback_editor.update_config(config.feedback)
        self.disturbance_editor.update_config(config.disturbance)

    def _update_command_config(self, config: ExperimentConfig) -> None:
        command = config.command
        command.amplitude = self.command_amplitude.value()
        command.offset = self.command_offset.value()
        command.frequency = self.command_frequency.value()
        command.start_time = self.command_start.value()
        command.rise_time = self.command_rise.value()
        command.hold_time = self.command_hold.value()
        command.manual_value = self.command_manual.value()
        simulation = config.simulation
        simulation.dt = self.sim_dt.value()
        simulation.duration = self.sim_duration.value()
        simulation.plot_interval = max(self.plot_interval.value(), simulation.dt)
        simulation.realtime_factor = self.realtime_factor.value()

    def _update_motor_config(self, config: ExperimentConfig) -> None:
        motor = config.motor
        for name, widget in zip(
            ("resistance", "ld", "lq", "flux", "pole_pairs", "inertia", "viscous", "dc_voltage", "current_limit"),
            self._motor_fields(),
        ):
            setattr(motor, name, widget.value())

    def _update_control_config(self, config: ExperimentConfig) -> None:
        self.current_d_pid.update_config(config.control.current_d)
        self.current_q_pid.update_config(config.control.current)
        self.speed_pid.update_config(config.control.speed)
        self.position_pid.update_config(config.control.position)
        config.control.current_feedforward = self.ff_current.isChecked()
        config.control.speed_feedforward = self.ff_speed.isChecked()
        config.control.position_feedforward = self.ff_position.isChecked()

    def load_config(self, config: ExperimentConfig) -> None:
        self.config = config
        self._loading = True
        self.experiment_name.setText(config.name)
        self.mode_combo.setCurrentText(config.control.mode.value)
        self.set_reference_options(config.control.mode, config.command.reference_type)
        self.command_combo.setCurrentText(config.command.kind.value)
        self.current_test.load(config.command.current_axis, config.command.lock_rotor)
        self._load_primary_fields(config)
        self.current_d_pid.load_config(config.control.current_d)
        self.current_q_pid.load_config(config.control.current)
        self.speed_pid.load_config(config.control.speed)
        self.position_pid.load_config(config.control.position)
        self.ff_current.setChecked(config.control.current_feedforward)
        self.ff_speed.setChecked(config.control.speed_feedforward)
        self.ff_position.setChecked(config.control.position_feedforward)
        self.feedback_editor.load_config(config.feedback)
        self.disturbance_editor.load_config(config.disturbance)
        self._loading = False
        self.update_command_units(config.command.reference_type)
        self.update_current_test_controls(config.control.mode, config.command.current_axis)

    def _load_primary_fields(self, config: ExperimentConfig) -> None:
        fields = (
            self.command_amplitude, self.command_offset, self.command_frequency,
            self.command_start, self.command_rise, self.command_hold, self.command_manual,
            self.sim_dt, self.sim_duration, self.plot_interval, self.realtime_factor,
            *self._motor_fields(),
        )
        values = (
            config.command.amplitude, config.command.offset, config.command.frequency,
            config.command.start_time, config.command.rise_time, config.command.hold_time,
            config.command.manual_value, config.simulation.dt, config.simulation.duration,
            config.simulation.plot_interval, config.simulation.realtime_factor,
            config.motor.resistance, config.motor.ld, config.motor.lq, config.motor.flux,
            config.motor.pole_pairs, config.motor.inertia, config.motor.viscous,
            config.motor.dc_voltage, config.motor.current_limit,
        )
        for widget, value in zip(fields, values):
            widget.setValue(value)

    def set_reference_options(
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

    def update_command_units(self, reference_type: ReferenceType) -> None:
        unit = " A" if reference_type == ReferenceType.CURRENT else " rpm" if reference_type == ReferenceType.SPEED else " rad"
        for field in (self.command_amplitude, self.command_offset, self.command_manual):
            field.setSuffix(unit)

    def update_current_test_controls(
        self,
        mode: LoopMode,
        axis: CurrentAxis | None = None,
    ) -> None:
        enabled = mode == LoopMode.CURRENT
        self.current_test.setVisible(enabled)
        if not enabled:
            self.command_group.setTitle("指令发生器")
            self.command_labels[self.command_amplitude].setText("幅值")
            self.command_labels[self.command_offset].setText("偏置")
            self.command_labels[self.command_manual].setText("手动值")
            return
        selected = axis or (CurrentAxis.D if self.axis_d.isChecked() else CurrentAxis.Q)
        symbol = "Id" if selected == CurrentAxis.D else "Iq"
        inactive = "Iq" if selected == CurrentAxis.D else "Id"
        self.command_group.setTitle(f"{symbol} 指令发生器")
        self.command_labels[self.command_amplitude].setText(f"{symbol} 幅值")
        self.command_labels[self.command_offset].setText(f"{symbol} 偏置")
        self.command_labels[self.command_manual].setText(f"{symbol} 手动值")
        self.current_test.update_hint(selected)
        self.current_axis_tabs.setCurrentIndex(0 if selected == CurrentAxis.D else 1)

    def _current_test_changed(self) -> None:
        self.update_current_test_controls(
            LoopMode(self.mode_combo.currentText()), self.current_test.selected_axis()
        )
        self._field_changed()

    def _motor_fields(self):
        return (
            self.motor_r, self.motor_ld, self.motor_lq, self.motor_flux, self.motor_poles,
            self.motor_inertia, self.motor_viscous, self.motor_voltage, self.motor_current,
        )
