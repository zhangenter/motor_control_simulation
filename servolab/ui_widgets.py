from __future__ import annotations

from bisect import bisect_left
from typing import Callable

import pyqtgraph as pg
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import LoopMode, PIDConfig, ReferenceType, has_position_outer_loop
from .theme import PLOT_COLORS


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    """Only adjust the value with the wheel while the field has focus."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FocusWheelSpinBox(QSpinBox):
    """Only adjust the value with the wheel while the field has focus."""

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


def make_double(
    value: float,
    minimum: float = -1e6,
    maximum: float = 1e6,
    decimals: int = 5,
    step: float = 0.1,
    suffix: str = "",
) -> QDoubleSpinBox:
    box = FocusWheelDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


def make_int(value: int, minimum: int = 0, maximum: int = 1_000_000, suffix: str = "") -> QSpinBox:
    box = FocusWheelSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


class ValueCard(QFrame):
    def __init__(self, title: str, unit: str, color: str = "#edf8f6", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ValueCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(1)
        title_label = QLabel(title.upper())
        title_label.setObjectName("SectionTitle")
        self.value_label = QLabel("0.000")
        self.value_label.setObjectName("ValueLarge")
        self.value_label.setStyleSheet(f"color: {color};")
        unit_label = QLabel(unit)
        unit_label.setObjectName("ValueUnit")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(unit_label)

    def set_value(self, value: float, precision: int = 3) -> None:
        if abs(value) >= 10000:
            text = f"{value:.2e}"
        else:
            text = f"{value:.{precision}f}"
        self.value_label.setText(text)


class TopologyWidget(QWidget):
    """Compact, custom-painted view of the currently active loop topology."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = LoopMode.CASCADE
        self.reference_type = ReferenceType.POSITION
        self.setMinimumHeight(100)
        self.setMaximumHeight(112)

    def set_mode(self, mode: LoopMode) -> None:
        self.mode = mode
        self.update()

    def set_reference_type(self, reference_type: ReferenceType) -> None:
        self.reference_type = reference_type
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1417"))
        painter.setPen(QPen(QColor("#26373d"), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
        title_font = QFont(self.font())
        title_font.setPixelSize(9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#70868d"))
        painter.drawText(13, 18, "ACTIVE CONTROL TOPOLOGY")

        mode_nodes = {
            LoopMode.CURRENT: ["电流 PI", "PMSM"],
            LoopMode.SPEED: ["速度 PID", "PMSM"],
            LoopMode.POSITION: ["位置 PID", "PMSM"],
            LoopMode.CURRENT_SPEED: ["速度 PID", "电流 PI", "PMSM"],
            LoopMode.CURRENT_POSITION: ["位置 PID", "电流 PI", "PMSM"],
            LoopMode.SPEED_POSITION: ["位置 PID", "速度 PID", "PMSM"],
            LoopMode.CASCADE: ["位置 PID", "速度 PID", "电流 PI", "PMSM"],
        }
        input_labels = {
            ReferenceType.POSITION: "位置指令",
            ReferenceType.SPEED: "速度指令",
            ReferenceType.CURRENT: "电流指令",
        }
        nodes = [input_labels[self.reference_type]]
        if self.reference_type == ReferenceType.SPEED and has_position_outer_loop(self.mode):
            nodes.append("积分 ∫")
        nodes.extend(mode_nodes[self.mode])
        left, right = 16.0, self.width() - 16.0
        gap = 13.0
        node_width = (right - left - gap * (len(nodes) - 1)) / len(nodes)
        y, height = 39.0, 43.0
        body_font = QFont(self.font())
        body_font.setPixelSize(11)
        painter.setFont(body_font)
        for index, label in enumerate(nodes):
            x = left + index * (node_width + gap)
            rect = QRectF(x, y, node_width, height)
            fill = QColor("#173029") if index not in (0, len(nodes) - 1) else QColor("#172329")
            edge = QColor("#45c9a5") if index not in (0, len(nodes) - 1) else QColor("#3c555e")
            painter.setBrush(fill)
            painter.setPen(QPen(edge, 1))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("#dbe8e8"))
            painter.drawText(rect, Qt.AlignCenter, label)
            if index < len(nodes) - 1:
                x1, x2 = rect.right() + 2, rect.right() + gap - 2
                center_y = rect.center().y()
                painter.setPen(QPen(QColor("#5a767d"), 1.2))
                painter.drawLine(int(x1), int(center_y), int(x2), int(center_y))
                painter.drawLine(int(x2 - 4), int(center_y - 3), int(x2), int(center_y))
                painter.drawLine(int(x2 - 4), int(center_y + 3), int(x2), int(center_y))


class PIDEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, config: PIDConfig, unit: str, parent: QWidget | None = None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(10, 12, 10, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        self.kp = make_double(config.kp, 0, 1e6, 5, 0.1)
        self.ki = make_double(config.ki, 0, 1e7, 5, 1.0)
        self.kd = make_double(config.kd, 0, 1e6, 6, 0.01)
        self.kff = make_double(config.kff, -1e6, 1e6, 5, 0.01)
        self.output_limit = make_double(config.output_limit, 0, 1e6, 4, 1.0, f" {unit}")
        self.integral_limit = make_double(config.integral_limit, 0, 1e6, 4, 1.0)
        self.filter_enabled = QCheckBox("启用测量低通滤波")
        self.filter_enabled.setChecked(config.low_pass_enabled)
        self.filter_alpha = make_double(config.low_pass_alpha, 0.001, 1.0, 3, 0.05)
        for label, widget in (
            ("比例 Kp", self.kp),
            ("积分 Ki", self.ki),
            ("微分 Kd", self.kd),
            ("前馈 Kff", self.kff),
            ("输出限幅", self.output_limit),
            ("积分限幅", self.integral_limit),
            ("滤波系数 α", self.filter_alpha),
        ):
            form.addRow(label, widget)
        form.addRow("", self.filter_enabled)
        for widget in (
            self.kp,
            self.ki,
            self.kd,
            self.kff,
            self.output_limit,
            self.integral_limit,
            self.filter_alpha,
        ):
            widget.valueChanged.connect(self.changed)
        self.filter_enabled.toggled.connect(self.changed)

    def update_config(self, config: PIDConfig) -> None:
        config.kp = self.kp.value()
        config.ki = self.ki.value()
        config.kd = self.kd.value()
        config.kff = self.kff.value()
        config.output_limit = self.output_limit.value()
        config.integral_limit = self.integral_limit.value()
        config.low_pass_enabled = self.filter_enabled.isChecked()
        config.low_pass_alpha = self.filter_alpha.value()

    def load_config(self, config: PIDConfig) -> None:
        widgets_values = (
            (self.kp, config.kp),
            (self.ki, config.ki),
            (self.kd, config.kd),
            (self.kff, config.kff),
            (self.output_limit, config.output_limit),
            (self.integral_limit, config.integral_limit),
            (self.filter_alpha, config.low_pass_alpha),
        )
        for widget, value in widgets_values:
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.filter_enabled.blockSignals(True)
        self.filter_enabled.setChecked(config.low_pass_enabled)
        self.filter_enabled.blockSignals(False)


class PlotDashboard(QTabWidget):
    CURSOR_UNITS = {
        "position_ref": "rad",
        "position": "rad",
        "position_error": "rad",
        "speed_ref": "rpm",
        "user_speed_ref": "rpm",
        "speed": "rpm",
        "speed_error": "rpm",
        "current_ref": "A",
        "iq": "A",
        "id": "A",
        "vq": "V",
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
                ("position", "位置反馈", PLOT_COLORS["feedback"]),
                ("position_error", "位置误差", PLOT_COLORS["error"]),
            ),
        ),
        (
            "速度",
            "rpm",
            (
                ("user_speed_ref", "用户速度输入", PLOT_COLORS["disturbance"]),
                ("speed_ref", "速度指令", PLOT_COLORS["reference"]),
                ("speed", "速度反馈", PLOT_COLORS["feedback"]),
                ("speed_error", "速度误差", PLOT_COLORS["error"]),
            ),
        ),
        (
            "电流 / 电压",
            "A / V",
            (
                ("current_ref", "Iq 指令", PLOT_COLORS["reference"]),
                ("iq", "Iq 反馈", PLOT_COLORS["feedback"]),
                ("id", "Id 反馈", PLOT_COLORS["secondary"]),
                ("vq", "Vq", PLOT_COLORS["disturbance"]),
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
        self.cursor_items: dict[pg.PlotWidget, tuple[pg.InfiniteLine, pg.InfiniteLine, pg.TextItem]] = {}
        self.cursor_proxies: list[pg.SignalProxy] = []
        self.manual_line: pg.InfiniteLine | None = None
        self.manual_plot: pg.PlotWidget | None = None
        self.manual_callback: Callable[[float], None] | None = None
        self._manual_guard = False
        self._input_display_signature: tuple[ReferenceType, bool] | None = None
        for title, unit, signals in self.PLOT_SPECS:
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
                curve = plot.plot([], [], name=label, pen=pg.mkPen(color, width=1.8))
                self.curves[key] = curve
                check = QCheckBox(label)
                check.setChecked(True)
                check.setStyleSheet(f"color: {color};")
                check.toggled.connect(curve.setVisible)
                self.channel_checks[key] = check
                channel_bar.addWidget(check)
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
            group: list[tuple[pg.PlotWidget, pg.PlotDataItem]] = []
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
        show_converted_speed = reference_type == ReferenceType.SPEED and position_outer
        check = self.channel_checks["user_speed_ref"]
        check.blockSignals(True)
        check.setChecked(show_converted_speed)
        check.blockSignals(False)
        self.curves["user_speed_ref"].setVisible(show_converted_speed)

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
            vertical.hide()
            horizontal.hide()
            label.hide()
            return

        point = view_box.mapSceneToView(position)
        sample_time, readings = self._cursor_readings(plot, point.x())
        if sample_time is None or not readings:
            vertical.hide()
            horizontal.hide()
            label.hide()
            return

        selected = min(readings, key=lambda reading: abs(reading[2] - point.y()))
        selected_key, _selected_name, selected_value = selected
        lines = [f"t = {sample_time:.6g} s"]
        for key, name, value in readings:
            marker = "▸" if key == selected_key else " "
            unit = self.CURSOR_UNITS.get(key, "")
            suffix = f" {unit}" if unit else ""
            lines.append(f"{marker} {name} = {value:.6g}{suffix}")

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

    def _cursor_readings(
        self,
        plot: pg.PlotWidget,
        cursor_time: float,
    ) -> tuple[float | None, list[tuple[str, str, float]]]:
        """Return visible channel values at the data sample nearest to the cursor."""
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

        readings: list[tuple[str, str, float]] = []
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
    ) -> None:
        if reference_type == ReferenceType.CURRENT:
            plot_index = 2
        elif reference_type == ReferenceType.SPEED:
            plot_index = 1
        else:
            plot_index = 0
        target_plot = self.plots[plot_index]
        self.manual_callback = callback
        if not enabled:
            if self.manual_line is not None and self.manual_plot is not None:
                self.manual_plot.removeItem(self.manual_line)
            self.manual_line = None
            self.manual_plot = None
            return
        if self.manual_line is not None and self.manual_plot is target_plot:
            self._manual_guard = True
            self.manual_line.setPos(value)
            self._manual_guard = False
            return
        if self.manual_line is not None and self.manual_plot is not None:
            self.manual_plot.removeItem(self.manual_line)
        self.manual_plot = target_plot
        self.manual_line = pg.InfiniteLine(
            pos=value,
            angle=0,
            movable=True,
            pen=pg.mkPen(PLOT_COLORS["reference"], width=2),
            hoverPen=pg.mkPen("#fff1b7", width=3),
        )
        self.manual_line.setZValue(15)
        self.manual_line.sigPositionChanged.connect(self._manual_position_changed)
        target_plot.addItem(self.manual_line)

    def _manual_position_changed(self, line: pg.InfiniteLine) -> None:
        if not self._manual_guard and self.manual_callback is not None:
            self.manual_callback(float(line.value()))


class SwitchRow(QWidget):
    changed = pyqtSignal()

    def __init__(self, text: str, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        self.check = QCheckBox("启用")
        self.check.setChecked(checked)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(self.check)
        self.check.toggled.connect(self.changed)
