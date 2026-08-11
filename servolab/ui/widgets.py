from __future__ import annotations

from PyQt5.QtCore import QLocale, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import PIDConfig


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
    # Control parameters and experiment files consistently use a dot as the
    # decimal separator.  Do not let the desktop locale turn it into a group
    # separator (for example, interpreting "0.25" as an invalid value).
    box.setLocale(QLocale.c())
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


def make_int(
    value: int,
    minimum: int = 0,
    maximum: int = 1_000_000,
    suffix: str = "",
) -> QSpinBox:
    box = FocusWheelSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    return box


class ValueCard(QFrame):
    def __init__(
        self,
        title: str,
        unit: str,
        color: str = "#edf8f6",
        parent: QWidget | None = None,
    ):
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
        text = f"{value:.2e}" if abs(value) >= 10000 else f"{value:.{precision}f}"
        self.value_label.setText(text)


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
