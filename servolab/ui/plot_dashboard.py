from __future__ import annotations

from bisect import bisect_left
from typing import Callable

import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from ..config import CurrentAxis, ReferenceType
from .theme import PLOT_COLORS


class PlotDashboard(QTabWidget):
    CURSOR_UNITS = {
        "position_ref": "rad",
        "position": "rad",
        "position_actual": "rad",
        "position_error": "rad",
        "speed_ref": "rpm",
        "user_speed_ref": "rpm",
        "speed": "rpm",
        "speed_actual": "rpm",
        "speed_error": "rpm",
        "current_ref": "A",
        "id_ref": "A",
        "iq_ref": "A",
        "iq": "A",
        "id": "A",
        "vq": "V",
        "vd": "V",
        "applied_vq": "V",
        "applied_vd": "V",
        "bus_voltage": "V",
        "voltage_limit": "V",
        "torque": "N·m",
        "load_torque": "N·m",
        "friction_torque": "N·m",
        "cogging_torque": "N·m",
        "pid_p": "output",
        "pid_i": "output",
        "pid_d": "output",
    }

    PLOT_SPECS = (
        (
            "位置",
            "rad",
            (
                ("position_ref", "位置指令", PLOT_COLORS["reference"]),
                ("position", "编码器位置", PLOT_COLORS["feedback"]),
                ("position_error", "位置误差", PLOT_COLORS["error"]),
            ),
        ),
        (
            "速度",
            "rpm",
            (
                ("user_speed_ref", "用户速度输入", PLOT_COLORS["disturbance"]),
                ("speed_ref", "速度指令", PLOT_COLORS["reference"]),
                ("speed", "估算速度", PLOT_COLORS["feedback"]),
                ("speed_actual", "实际速度", PLOT_COLORS["secondary"]),
                ("speed_error", "速度误差", PLOT_COLORS["error"]),
            ),
        ),
        (
            "dq 电流",
            "A",
            (
                ("id_ref", "Id*", PLOT_COLORS["secondary"]),
                ("id", "Id", PLOT_COLORS["feedback"]),
                ("iq_ref", "Iq*", PLOT_COLORS["reference"]),
                ("iq", "Iq", PLOT_COLORS["disturbance"]),
            ),
        ),
        (
            "dq 电压",
            "V",
            (
                ("vd", "Vd", PLOT_COLORS["secondary"]),
                ("vq", "Vq", PLOT_COLORS["reference"]),
                ("applied_vd", "实际 Vd", PLOT_COLORS["feedback"]),
                ("applied_vq", "实际 Vq", PLOT_COLORS["disturbance"]),
                ("bus_voltage", "母线电压", PLOT_COLORS["muted"]),
                ("voltage_limit", "电压限幅", PLOT_COLORS["error"]),
            ),
        ),
        (
            "转矩 / 干扰",
            "N·m",
            (
                ("torque", "电磁转矩", PLOT_COLORS["feedback"]),
                ("load_torque", "负载转矩", PLOT_COLORS["reference"]),
                ("friction_torque", "摩擦转矩", PLOT_COLORS["error"]),
                ("cogging_torque", "齿槽转矩", PLOT_COLORS["disturbance"]),
            ),
        ),
        (
            "PID 分量",
            "output",
            (
                ("pid_p", "P 分量", PLOT_COLORS["feedback"]),
                ("pid_i", "I 分量", PLOT_COLORS["reference"]),
                ("pid_d", "D 分量", PLOT_COLORS["secondary"]),
            ),
        ),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, background="#0d1417", foreground="#7f9298")
        self.plots: list[pg.PlotWidget] = []
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.channel_checks: dict[str, QCheckBox] = {}
        self.plot_signals: dict[pg.PlotWidget, tuple[tuple[str, str, str], ...]] = {}
        self.display_data: dict[str, tuple[list[float], list[float]]] = {}
        self.overlay_curves: list[list[tuple[pg.PlotWidget, pg.PlotDataItem]]] = []
        self.cursor_items = {}
        self.cursor_proxies: list[pg.SignalProxy] = []
        self.manual_line: pg.InfiniteLine | None = None
        self.manual_plot: pg.PlotWidget | None = None
        self.manual_callback: Callable[[float], None] | None = None
        self._manual_guard = False
        self._input_display_signature: tuple[ReferenceType, bool] | None = None
        self.current_axis: CurrentAxis | None = None
        for title, unit, signals in self.PLOT_SPECS:
            self._add_plot_page(title, unit, signals)
        for key in ("applied_vd", "applied_vq", "bus_voltage"):
            self.channel_checks[key].setChecked(False)

    def _add_plot_page(self, title: str, unit: str, signals) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        channel_bar = QHBoxLayout()
        channel_bar.setContentsMargins(9, 5, 9, 5)
        channel_bar.setSpacing(14)
        channel_title = QLabel("显示通道")
        channel_title.setObjectName("SectionTitle")
        channel_bar.addWidget(channel_title)
        plot = pg.PlotWidget()
        plot.setLabel("bottom", "时间", units="s")
        plot.setLabel("left", title, units=unit)
        plot.showGrid(x=True, y=True, alpha=0.16)
        plot.addLegend(offset=(8, 8), labelTextColor="#9eb0b5")
        plot.setDownsampling(auto=True, mode="peak")
        plot.setClipToView(True)
        for key, label, color in signals:
            self._add_channel(plot, channel_bar, key, label, color)
        channel_bar.addStretch()
        hint = QLabel("游标读取 · 滚轮缩放 · 拖动平移")
        hint.setStyleSheet("color: #536970;")
        channel_bar.addWidget(hint)
        page_layout.addLayout(channel_bar)
        page_layout.addWidget(plot, 1)
        self.plots.append(plot)
        self.plot_signals[plot] = signals
        self._install_cursor(plot)
        self.addTab(page, title)

    def _add_channel(self, plot, channel_bar, key: str, label: str, color: str) -> None:
        curve = plot.plot([], [], name=label, pen=pg.mkPen(color, width=1.8))
        self.curves[key] = curve
        check = QCheckBox(label)
        check.setChecked(True)
        check.setStyleSheet(f"color: {color};")
        check.toggled.connect(curve.setVisible)
        self.channel_checks[key] = check
        channel_bar.addWidget(check)

    def update_data(self, history: dict[str, list[float]]) -> None:
        time_values = history.get("time", [])
        start = max(0, len(time_values) - 12000)
        x = time_values[start:]
        for key, curve in self.curves.items():
            y = history.get(key, [])[start:]
            curve.setData(x, y)
            self.display_data[key] = (x, y)

    def set_overlays(self, overlays: list[tuple[str, dict[str, list[float]]]]) -> None:
        for group in self.overlay_curves:
            for plot, curve in group:
                plot.removeItem(curve)
        self.overlay_curves.clear()
        overlay_palette = ("#718f98", "#b68567", "#8778aa", "#6f9b78")
        for overlay_index, (name, history) in enumerate(overlays[-4:]):
            color = overlay_palette[overlay_index % len(overlay_palette)]
            group = []
            time_values = history.get("time", [])
            for plot, (_title, _unit, signals) in zip(self.plots, self.PLOT_SPECS):
                for signal_index, (key, label, _signal_color) in enumerate(signals):
                    curve = plot.plot(
                        time_values,
                        history.get(key, []),
                        name=f"{name} · {label}" if signal_index == 0 else None,
                        pen=pg.mkPen(color, width=1.0, style=Qt.DashLine),
                    )
                    curve.setOpacity(0.52 if signal_index == 0 else 0.25)
                    group.append((plot, curve))
            self.overlay_curves.append(group)

    def current_plot(self) -> pg.PlotWidget:
        return self.plots[self.currentIndex()]

    def set_input_reference(self, reference_type: ReferenceType, position_outer: bool) -> None:
        signature = (reference_type, position_outer)
        if signature == self._input_display_signature:
            return
        self._input_display_signature = signature
        show_speed = reference_type == ReferenceType.SPEED and position_outer
        check = self.channel_checks["user_speed_ref"]
        check.blockSignals(True)
        check.setChecked(show_speed)
        check.blockSignals(False)
        self.curves["user_speed_ref"].setVisible(show_speed)

    def set_current_axis(self, axis: CurrentAxis) -> None:
        if axis == self.current_axis:
            return
        self.current_axis = axis
        active_channels = {
            CurrentAxis.D: {"id_ref", "id"},
            CurrentAxis.Q: {"iq_ref", "iq"},
        }[axis]
        for key in ("id_ref", "id", "iq_ref", "iq"):
            active = key in active_channels
            check = self.channel_checks[key]
            check.blockSignals(True)
            check.setChecked(active)
            check.blockSignals(False)
            self.curves[key].setVisible(active)

    def _install_cursor(self, plot: pg.PlotWidget) -> None:
        pen = pg.mkPen("#587078", width=1, style=Qt.DotLine)
        vertical = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        horizontal = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        label = pg.TextItem(color="#c3d1d3", anchor=(0, 1), fill=pg.mkBrush(13, 20, 23, 220))
        for item in (vertical, horizontal, label):
            item.setZValue(20)
            item.hide()
            plot.addItem(item, ignoreBounds=True)
        self.cursor_items[plot] = (vertical, horizontal, label)
        proxy = pg.SignalProxy(
            plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=lambda event, current_plot=plot: self._cursor_moved(current_plot, event),
        )
        self.cursor_proxies.append(proxy)

    def _cursor_moved(self, plot: pg.PlotWidget, event) -> None:
        position = event[0]
        vertical, horizontal, label = self.cursor_items[plot]
        view_box = plot.plotItem.vb
        if not view_box.sceneBoundingRect().contains(position):
            self._hide_cursor(vertical, horizontal, label)
            return
        point = view_box.mapSceneToView(position)
        sample_time, readings = self._cursor_readings(plot, point.x())
        if sample_time is None or not readings:
            self._hide_cursor(vertical, horizontal, label)
            return
        selected = min(readings, key=lambda reading: abs(reading[2] - point.y()))
        selected_key, _selected_name, selected_value = selected
        lines = [f"t = {sample_time:.6g} s"]
        for key, name, value in readings:
            marker = "▸" if key == selected_key else " "
            unit = self.CURSOR_UNITS.get(key, "")
            lines.append(f"{marker} {name} = {value:.6g}{f' {unit}' if unit else ''}")
        vertical.setPos(sample_time)
        horizontal.setPos(selected_value)
        label.setText("\n".join(lines))
        x_range, y_range = view_box.viewRange()
        label.setAnchor(
            (
                1 if sample_time > sum(x_range) / 2 else 0,
                0 if selected_value > sum(y_range) / 2 else 1,
            )
        )
        label.setPos(sample_time, selected_value)
        vertical.show()
        horizontal.show()
        label.show()

    @staticmethod
    def _hide_cursor(vertical, horizontal, label) -> None:
        vertical.hide()
        horizontal.hide()
        label.hide()

    def _cursor_readings(
        self,
        plot: pg.PlotWidget,
        cursor_time: float,
    ) -> tuple[float | None, list[tuple[str, str, float]]]:
        signals = self.plot_signals[plot]
        visible_signals = [
            (key, name)
            for key, name, _color in signals
            if self.channel_checks[key].isChecked() and key in self.display_data
        ]
        if not visible_signals:
            return None, []
        reference_x = self.display_data[visible_signals[0][0]][0]
        if not reference_x:
            return None, []
        index = self._nearest_index(reference_x, cursor_time)
        sample_time = float(reference_x[index])
        readings = []
        for key, name in visible_signals:
            x_values, y_values = self.display_data[key]
            if not x_values or not y_values:
                continue
            value_index = self._nearest_index(x_values, sample_time)
            if value_index < len(y_values):
                readings.append((key, name, float(y_values[value_index])))
        return sample_time, readings

    @staticmethod
    def _nearest_index(values: list[float], target: float) -> int:
        index = bisect_left(values, target)
        if index <= 0:
            return 0
        if index >= len(values):
            return len(values) - 1
        before = index - 1
        return before if target - values[before] <= values[index] - target else index

    def set_manual_control(
        self,
        enabled: bool,
        reference_type: ReferenceType,
        value: float,
        callback: Callable[[float], None],
        current_axis: CurrentAxis = CurrentAxis.Q,
    ) -> None:
        plot_index = 2 if reference_type == ReferenceType.CURRENT else 1 if reference_type == ReferenceType.SPEED else 0
        target_plot = self.plots[plot_index]
        self.manual_callback = callback
        if not enabled:
            self._remove_manual_line()
            return
        if self.manual_line is not None and self.manual_plot is target_plot:
            self._manual_guard = True
            self.manual_line.setPos(value)
            self._manual_guard = False
            return
        self._remove_manual_line()
        self.manual_plot = target_plot
        self.manual_line = pg.InfiniteLine(
            pos=value,
            angle=0,
            movable=True,
            pen=pg.mkPen(PLOT_COLORS["reference"], width=2),
            hoverPen=pg.mkPen("#fff1b7", width=3),
        )
        if reference_type == ReferenceType.CURRENT:
            axis_name = "Id" if current_axis == CurrentAxis.D else "Iq"
            self.manual_line.setToolTip(f"拖动设置 {axis_name} 手动值")
        self.manual_line.setZValue(15)
        self.manual_line.sigPositionChanged.connect(self._manual_position_changed)
        target_plot.addItem(self.manual_line)

    def _remove_manual_line(self) -> None:
        if self.manual_line is not None and self.manual_plot is not None:
            self.manual_plot.removeItem(self.manual_line)
        self.manual_line = None
        self.manual_plot = None

    def _manual_position_changed(self, line: pg.InfiniteLine) -> None:
        if not self._manual_guard and self.manual_callback is not None:
            self.manual_callback(float(line.value()))

    def shutdown(self) -> None:
        for proxy in self.cursor_proxies:
            proxy.disconnect()
        self.cursor_proxies.clear()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)
