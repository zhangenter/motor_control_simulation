from __future__ import annotations

import math
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    CommandType,
    CurrentAxis,
    ExperimentConfig,
    LoopMode,
    ReferenceType,
    has_position_outer_loop,
)
from ..control import CustomControllerError
from ..services import ControllerGenerationOptions, SimulationSession, generate_custom_controller_code
from .custom_controller_dialog import CustomControllerDialog, CustomControllerManager
from .file_actions import DesktopFileActions
from .menu_actions import ApplicationMenuController
from .parameter_panel import ParameterPanel
from .plot_dashboard import PlotDashboard
from .topology import TopologyWidget
from .window_shell import build_bottom_panel, build_header, build_right_panel, build_status_bar


class ServoLabWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ServoLab · PMSM 伺服电机控制示教器")
        self.resize(1540, 960)
        self.setMinimumSize(1180, 760)
        self.session = SimulationSession(ExperimentConfig())
        self._last_wall_time = time.perf_counter()
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

    @property
    def config(self):
        return self.session.config

    @property
    def simulation(self):
        return self.session.simulation

    @property
    def custom_process(self):
        return self.session.custom_controller

    @property
    def running(self) -> bool:
        return self.session.running

    @running.setter
    def running(self, value: bool) -> None:
        self.session.running = value

    @property
    def overlays(self):
        return self.session.overlays

    @property
    def _custom_code_needs_compile(self) -> bool:
        return self.custom_controller.needs_compile

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(build_header(self))
        self.parameters = ParameterPanel(self.config)
        self.parameters.changed.connect(self._form_changed)
        self.parameters.trajectory_requested.connect(self.load_trajectory)
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.horizontal_splitter = QSplitter(Qt.Horizontal)
        self.right_panel = build_right_panel(self)
        self.bottom_panel = build_bottom_panel(self)
        self.horizontal_splitter.addWidget(self.parameters)
        self.horizontal_splitter.addWidget(self._build_center_panel())
        self.horizontal_splitter.addWidget(self.right_panel)
        self.horizontal_splitter.setHandleWidth(5)
        self.horizontal_splitter.setStretchFactor(0, 0)
        self.horizontal_splitter.setStretchFactor(1, 1)
        self.horizontal_splitter.setStretchFactor(2, 0)
        self.horizontal_splitter.setSizes([330, 900, 260])
        self.vertical_splitter.addWidget(self.horizontal_splitter)
        self.vertical_splitter.addWidget(self.bottom_panel)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)
        self.vertical_splitter.setSizes([720, 220])
        root_layout.addWidget(self.vertical_splitter)
        self.setCentralWidget(root)
        build_status_bar(self)
        self._create_coordinators()
        self._expose_compatibility_widgets()

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(480)
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 10, 4, 4)
        self.topology = TopologyWidget()
        self.plots = PlotDashboard()
        layout.addWidget(self.topology)
        layout.addWidget(self.plots, 1)
        return panel

    def _create_coordinators(self) -> None:
        initial_options = ControllerGenerationOptions(
            back_emf_compensation=True,
            dq_decoupling=True,
            anti_windup=True,
        )
        initial_code = generate_custom_controller_code(
            self.config.control.mode,
            self.config.command.reference_type,
            self.config.control,
            self.config.motor,
            initial_options,
            self.config.command.current_axis,
        )
        self.custom_dialog = CustomControllerDialog(initial_code, self)
        self.custom_controller = CustomControllerManager(
            self,
            self.custom_dialog,
            self.session,
            self.custom_summary_status,
            self._sync_config_from_form,
            self._log,
            self.pause_simulation,
        )
        self.open_custom_editor_button.clicked.connect(self.open_custom_controller_editor)
        self.file_actions = DesktopFileActions(
            self,
            self.session,
            self.parameters,
            self.plots,
            self._sync_config_from_form,
            self.pause_simulation,
            self._refresh_ui,
            self._log,
        )
        self.menu_actions = ApplicationMenuController(self)
        self.pid_calculator = self.menu_actions.pid_calculator

    def _expose_compatibility_widgets(self) -> None:
        for name in (
            "mode_combo", "reference_combo", "command_amplitude", "command_manual",
            "current_pid", "current_d_pid", "current_q_pid", "speed_pid", "position_pid",
        ):
            setattr(self, name, getattr(self.parameters, name))
        aliases = {
            "code_editor": "code_editor",
            "custom_file_label": "file_label",
            "save_custom_code_button": "save_button",
            "generate_custom_code_button": "generate_button",
            "enable_custom": "enable_checkbox",
            "generator_feedforward": "generator_feedforward",
            "generator_friction": "generator_friction",
        }
        for window_name, dialog_name in aliases.items():
            setattr(self, window_name, getattr(self.custom_dialog, dialog_name))

    def _connect_shortcuts(self) -> None:
        run_action = QAction(self)
        run_action.setShortcut(QKeySequence(Qt.Key_Space))
        run_action.triggered.connect(
            lambda: self.pause_simulation() if self.running else self.start_simulation()
        )
        self.addAction(run_action)
        reset_action = QAction(self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(self.reset_simulation)
        self.addAction(reset_action)

    def _form_changed(self) -> None:
        old_mode = self.config.control.mode
        old_reference = self.config.command.reference_type
        old_current_axis = self.config.command.current_axis
        selected_mode = LoopMode(self.parameters.mode_combo.currentText())
        if selected_mode != old_mode:
            self.parameters.set_reference_options(selected_mode, old_reference)
        self.parameters.sync_mode_dependent_controls(selected_mode)
        self._sync_config_from_form()
        self.topology.set_mode(self.config.control.mode)
        self.topology.set_reference_type(self.config.command.reference_type)
        self.topology.set_current_axis(self.config.command.current_axis)
        if old_mode != self.config.control.mode:
            self.controller_reset_for_mode()
            self._log(f"控制拓扑切换为：{self.config.control.mode.value}")
        if old_reference != self.config.command.reference_type:
            self.controller_reset_for_mode()
            self._log(f"用户输入切换为：{self.config.command.reference_type.value}")
        if old_current_axis != self.config.command.current_axis:
            self.controller_reset_for_mode()
            self._log(f"电流测试轴切换为：{self.config.command.current_axis.value} 轴")
        self._refresh_reference_controls()
        self.custom_controller.refresh_context()

    def _sync_config_from_form(self) -> None:
        self.parameters.update_config(self.config)
        self.simulation.disturbance.dt = self.config.simulation.dt
        self.simulation.encoder.dt = self.config.simulation.dt
        self.sample_status.setText(
            f"dt {self.config.simulation.dt * 1e6:.0f} μs  ·  "
            f"plot {self.config.simulation.plot_interval * 1e3:.1f} ms"
        )

    def _load_form_from_config(self) -> None:
        self.parameters.load_config(self.config)
        self._sync_config_from_form()
        self.topology.set_mode(self.config.control.mode)
        self.topology.set_reference_type(self.config.command.reference_type)
        self.topology.set_current_axis(self.config.command.current_axis)
        self._refresh_reference_controls()
        self.custom_controller.refresh_context()

    def _refresh_reference_controls(self) -> None:
        self.parameters.update_command_units(self.config.command.reference_type)
        self.parameters.update_current_test_controls(
            self.config.control.mode, self.config.command.current_axis
        )
        position_outer = has_position_outer_loop(self.config.control.mode)
        self.plots.set_input_reference(self.config.command.reference_type, position_outer)
        self.plots.set_current_axis(self.config.command.current_axis)
        self.plots.set_manual_control(
            self.config.command.kind == CommandType.MANUAL,
            self.config.command.reference_type,
            self.config.command.manual_value,
            self._manual_line_changed,
            self.config.command.current_axis,
        )

    def _manual_line_changed(self, value: float) -> None:
        self.parameters.command_manual.setValue(value)

    def controller_reset_for_mode(self) -> None:
        self.simulation.controller.reset()

    def start_simulation(self) -> None:
        self._sync_config_from_form()
        self.session.start()
        self._last_wall_time = time.perf_counter()
        self._set_run_state("● RUNNING", "RUNNING", "StatusRunning")
        self._log("实时仿真开始。")

    def pause_simulation(self) -> None:
        if self.running:
            self._log(f"仿真暂停于 t = {self.simulation.time:.4f} s。")
        self.session.pause()
        self._set_run_state("● PAUSED", "PAUSED", "StatusPaused")

    def reset_simulation(self) -> None:
        self._sync_config_from_form()
        self.session.reset()
        self._set_run_state("● STOPPED", "READY", "StatusStopped")
        self._refresh_ui()
        self._log("仿真状态与曲线已复位。")

    def _set_run_state(self, state_text: str, status_text: str, object_name: str) -> None:
        self.run_state.setText(state_text)
        self.run_state.setObjectName(object_name)
        self.run_state.style().unpolish(self.run_state)
        self.run_state.style().polish(self.run_state)
        self.status_message.setText(status_text)
        self.status_message.setObjectName(object_name)

    def single_step(self) -> None:
        self.pause_simulation()
        self._sync_config_from_form()
        try:
            self.session.step()
        except CustomControllerError as exc:
            self.custom_controller.handle_error(exc)
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
            self.session.step(steps)
        except CustomControllerError as exc:
            self.custom_controller.handle_error(exc)
            return
        if self.simulation.time >= self.config.simulation.duration:
            self.pause_simulation()
            self._log("已到达设定实验时长。")
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        sample = self.simulation.last_sample
        if sample:
            self.time_card.set_value(sample.get("time", 0.0), 4)
            self.position_card.set_value(sample.get("position_actual", sample.get("position", 0.0)), 4)
            self.speed_card.set_value(sample.get("speed_actual", sample.get("speed", 0.0)), 3)
            current_key = "id" if self.config.command.current_axis == CurrentAxis.D else "iq"
            self.current_card.set_value(sample.get(current_key, 0.0), 3)
            self.torque_card.set_value(sample.get("torque", 0.0), 4)
        history = self.simulation.history.data
        self.plots.update_data(history)
        self.metric_samples.setText(str(len(self.simulation.history)))
        self._update_metrics(history)

    def _update_metrics(self, history: dict[str, list[float]]) -> None:
        times = history.get("time", [])
        title, unit, feedback, target = self._metric_series(history)
        if not feedback:
            return
        error = [reference - actual for reference, actual in zip(target, feedback)]
        self.metric_peak_title.setText(f"{title}峰值")
        self.metric_rms_title.setText(f"{title}误差 RMS")
        self.metric_peak.setText(f"{max(abs(value) for value in feedback):.4f} {unit}")
        if error:
            rms = math.sqrt(sum(value * value for value in error) / len(error))
            self.metric_rms.setText(f"{rms:.5f} {unit}")
        settling = self._settling_time(times, target, feedback)
        self.metric_settle.setText("—" if settling is None else f"{settling:.3f} s")

    def _metric_series(self, history):
        reference_type = self.config.command.reference_type
        if reference_type == ReferenceType.SPEED:
            return "速度", "rpm", history.get("speed_actual", []), history.get("user_speed_ref", [])
        if reference_type == ReferenceType.CURRENT:
            if self.config.command.current_axis == CurrentAxis.D:
                return "Id", "A", history.get("id", []), history.get("id_ref", [])
            return "Iq", "A", history.get("iq", []), history.get("iq_ref", [])
        return "位置", "rad", history.get("position_actual", []), history.get("position_ref", [])

    @staticmethod
    def _settling_time(times, reference, feedback) -> float | None:
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

        def update_progress(value: float) -> None:
            progress.setValue(int(value * 100))
            QApplication.processEvents()
            if progress.wasCanceled():
                raise InterruptedError

        try:
            self.session.run_offline(progress=update_progress)
        except InterruptedError:
            self._log("离线仿真已由用户取消。")
        except CustomControllerError as exc:
            self.custom_controller.handle_error(exc)
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
        name = self.session.keep_comparison()
        if name is None:
            QMessageBox.information(self, "保留对比", "当前还没有可保留的仿真数据。")
            return
        self.plots.set_overlays(self.overlays)
        self._log(f"已保留对比曲线：{name}")

    def clear_comparisons(self) -> None:
        self.session.clear_comparisons()
        self.plots.set_overlays([])
        self._log("对比曲线已清除。")

    def load_trajectory(self) -> None:
        self.file_actions.load_trajectory()

    def save_experiment(self) -> None:
        self.file_actions.save_experiment()

    def load_experiment(self) -> None:
        self.file_actions.load_experiment()
        self._refresh_reference_controls()
        self.custom_controller.refresh_context()

    def export_data_menu(self) -> None:
        self.file_actions.show_export_menu()

    def export_csv(self) -> None:
        self.file_actions.export_csv()

    def export_plot(self) -> None:
        self.file_actions.export_plot()

    def open_custom_controller_editor(self) -> None:
        self.custom_controller.show_editor()

    def generate_custom_controller_from_configuration(self) -> None:
        self.custom_controller.generate()

    def save_custom_controller_code(self) -> bool:
        return self.custom_controller.save_source()

    def open_custom_controller_code(self) -> None:
        self.custom_controller.open_source()

    def compile_custom_controller(self) -> None:
        self.custom_controller.compile()

    def stop_custom_controller(self) -> None:
        self.custom_controller.stop()

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}]  {message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.plots.shutdown()
        self.custom_dialog.close()
        self.pid_calculator.close()
        self.session.close()
        event.accept()
