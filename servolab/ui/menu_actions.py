from __future__ import annotations

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction

from ..config import ExperimentConfig
from .pid_calculator_dialog import PIDCalculatorDialog


class ApplicationMenuController:
    """Build and coordinate the application drop-down menus."""

    def __init__(self, owner):
        self.owner = owner
        self.pid_calculator = PIDCalculatorDialog(owner)
        self.pid_calculator.pid_ready.connect(self.apply_pid)
        self._build_menu_bar()
        owner.parameters.auto_tune.setEnabled(True)
        owner.parameters.auto_tune.setText("打开 PID 计算器…")
        owner.parameters.auto_tune.clicked.connect(self.show_pid_calculator)

    def _build_menu_bar(self) -> None:
        menu_bar = self.owner.menuBar()
        menu_bar.setNativeMenuBar(False)
        experiment_menu = menu_bar.addMenu("实验")
        window_menu = menu_bar.addMenu("窗口")
        toolbox_menu = menu_bar.addMenu("工具箱")
        self.owner.new_experiment_action = self._action(
            "新建实验", "Ctrl+N", self.new_experiment, "创建采用默认参数的新实验"
        )
        self.owner.open_experiment_action = self._action(
            "打开实验…", "Ctrl+O", self.owner.load_experiment, "打开 JSON 实验配置"
        )
        self.owner.save_experiment_action = self._action(
            "保存实验…", "Ctrl+S", self.owner.save_experiment, "保存当前实验配置"
        )
        self.owner.exit_action = self._action(
            "退出", "Ctrl+Q", self.owner.close, "退出 ServoLab"
        )
        experiment_menu.addActions(
            (
                self.owner.new_experiment_action,
                self.owner.open_experiment_action,
                self.owner.save_experiment_action,
            )
        )
        experiment_menu.addSeparator()
        experiment_menu.addAction(self.owner.exit_action)
        self.owner.parameters_view_action = self._view_action(
            "实验参数", self.owner.parameters, "显示或隐藏实验参数面板"
        )
        self.owner.realtime_view_action = self._view_action(
            "实时状态", self.owner.right_panel, "显示或隐藏实时状态面板"
        )
        self.owner.log_view_action = self._bottom_tab_action(
            "运行日志", self.owner.log_tab_index, "显示或隐藏运行日志"
        )
        self.owner.custom_controller_view_action = self._bottom_tab_action(
            "自定义控制器",
            self.owner.custom_controller_tab_index,
            "显示或隐藏自定义控制器入口",
        )
        window_menu.addActions(
            (self.owner.parameters_view_action, self.owner.realtime_view_action)
        )
        window_menu.addSeparator()
        window_menu.addActions(
            (self.owner.log_view_action, self.owner.custom_controller_view_action)
        )
        self.owner.pid_calculator_action = self._action(
            "PID 计算器…", "Ctrl+Shift+P", self.show_pid_calculator, "计算三环 PID 参数"
        )
        toolbox_menu.addAction(self.owner.pid_calculator_action)

    def _action(self, text: str, shortcut: str, callback, status_tip: str) -> QAction:
        action = QAction(text, self.owner)
        action.setShortcut(QKeySequence(shortcut))
        action.setStatusTip(status_tip)
        action.triggered.connect(callback)
        return action

    def _view_action(self, text: str, widget, status_tip: str) -> QAction:
        action = QAction(text, self.owner)
        action.setCheckable(True)
        action.setChecked(True)
        action.setStatusTip(status_tip)
        action.toggled.connect(widget.setVisible)
        return action

    def _bottom_tab_action(self, text: str, index: int, status_tip: str) -> QAction:
        action = QAction(text, self.owner)
        action.setCheckable(True)
        action.setChecked(True)
        action.setStatusTip(status_tip)
        action.toggled.connect(
            lambda visible, tab_index=index: self._set_bottom_tab_visible(tab_index, visible)
        )
        return action

    def _set_bottom_tab_visible(self, index: int, visible: bool) -> None:
        self.owner.bottom_tabs.setTabVisible(index, visible)
        bottom_visible = (
            self.owner.log_view_action.isChecked()
            or self.owner.custom_controller_view_action.isChecked()
        )
        self.owner.bottom_panel.setVisible(bottom_visible)

    def new_experiment(self) -> None:
        owner = self.owner
        owner.pause_simulation()
        if owner.session.custom_controller.running:
            owner.custom_controller.stop()
        owner.session.apply_config(ExperimentConfig())
        owner.session.clear_comparisons()
        owner.plots.set_overlays([])
        owner._load_form_from_config()
        owner.session.reset()
        owner._set_run_state("● STOPPED", "READY", "StatusStopped")
        owner._refresh_ui()
        owner._log("已新建实验，并恢复默认模型与控制参数。")

    def show_pid_calculator(self) -> None:
        self.owner._sync_config_from_form()
        self.pid_calculator.prepare(self.owner.config.motor)
        self.pid_calculator.prepare_current_axis(
            self.owner.config.motor, self.owner.config.command.current_axis
        )
        self.pid_calculator.show()
        self.pid_calculator.raise_()
        self.pid_calculator.activateWindow()

    def apply_pid(self, loop: str, kp: float, ki: float, kd: float) -> None:
        current_editor = (
            self.owner.parameters.current_d_pid
            if self.pid_calculator.selected_current_axis().value == "d"
            else self.owner.parameters.current_q_pid
        )
        editors = {
            "current": current_editor,
            "speed": self.owner.parameters.speed_pid,
            "position": self.owner.parameters.position_pid,
        }
        current_label = f"{self.pid_calculator.selected_current_axis().value} 轴电流环"
        labels = {"current": current_label, "speed": "速度环", "position": "位置环"}
        editor = editors[loop]
        editor.kp.setValue(kp)
        editor.ki.setValue(ki)
        editor.kd.setValue(kd)
        applied = (editor.kp.value(), editor.ki.value(), editor.kd.value())
        self.owner.parameters.tabs.setCurrentIndex(2)
        self.owner.parameters.pid_tabs.setCurrentIndex(tuple(editors).index(loop))
        self.owner._sync_config_from_form()
        self.owner.controller_reset_for_mode()
        self.owner.custom_controller.refresh_context()
        self.owner._log(
            f"PID 计算结果已应用到{labels[loop]}："
            f"Kp={applied[0]:.6g}，Ki={applied[1]:.6g}，Kd={applied[2]:.6g}。"
        )
