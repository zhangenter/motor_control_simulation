from __future__ import annotations

from pathlib import Path
from typing import Callable

from pyqtgraph.exporters import ImageExporter
from PyQt5.QtWidgets import QDialog, QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from ..config import CommandType
from ..services import ExperimentService, ExportService, SimulationSession
from .parameter_panel import ParameterPanel
from .plot_dashboard import PlotDashboard


class DesktopFileActions:
    """Desktop dialogs around headless persistence and export services."""

    def __init__(
        self,
        parent,
        session: SimulationSession,
        parameters: ParameterPanel,
        plots: PlotDashboard,
        sync_config: Callable[[], None],
        pause: Callable[[], None],
        refresh: Callable[[], None],
        log: Callable[[str], None],
    ):
        self.parent = parent
        self.session = session
        self.parameters = parameters
        self.plots = plots
        self.sync_config = sync_config
        self.pause = pause
        self.refresh = refresh
        self.log = log

    def load_trajectory(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "载入轨迹",
            "",
            "CSV 轨迹 (*.csv);;所有文件 (*)",
        )
        if not path:
            return
        try:
            times, values = ExperimentService.load_trajectory(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.parent, "轨迹格式错误", str(exc))
            return
        self.session.config.command.trajectory_time = times
        self.session.config.command.trajectory_value = values
        self.parameters.command_combo.setCurrentText(CommandType.TRAJECTORY.value)
        self.log(f"已载入轨迹 {Path(path).name}，共 {len(times)} 点。")

    def save_experiment(self) -> None:
        self.sync_config()
        config = self.session.config
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "保存实验配置",
            f"{config.name}.json",
            "实验配置 (*.json)",
        )
        if not path:
            return
        try:
            ExperimentService.save(config, path)
        except OSError as exc:
            QMessageBox.critical(self.parent, "保存失败", str(exc))
            return
        self.log(f"实验配置已保存：{path}")

    def load_experiment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "打开实验配置",
            "",
            "实验配置 (*.json)",
        )
        if not path:
            return
        try:
            config = ExperimentService.load(path)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self.parent, "配置读取失败", str(exc))
            return
        self.pause()
        self.session.apply_config(config)
        self.parameters.load_config(config)
        self.refresh()
        self.log(f"已打开实验配置：{path}")

    def show_export_menu(self) -> None:
        dialog = QDialog(self.parent)
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
        if len(self.session.simulation.history) < 2:
            QMessageBox.information(self.parent, "导出数据", "当前没有足够的仿真数据。")
            return
        config = self.session.config
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "导出数据",
            f"{config.name}.csv",
            "CSV 数据 (*.csv)",
        )
        if not path:
            return
        try:
            ExportService.export_csv(self.session.simulation.history, path)
            self.log(f"数据已导出：{path}")
        except OSError as exc:
            QMessageBox.critical(self.parent, "导出失败", str(exc))

    def export_plot(self) -> None:
        config = self.session.config
        path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "导出当前曲线",
            f"{config.name}.png",
            "PNG 图片 (*.png)",
        )
        if not path:
            return
        try:
            exporter = ImageExporter(self.plots.current_plot().plotItem)
            exporter.parameters()["width"] = 1800
            exporter.export(path)
            self.log(f"曲线图片已导出：{path}")
        except Exception as exc:  # noqa: BLE001 - exporter error is shown to the user
            QMessageBox.critical(self.parent, "导出失败", str(exc))
