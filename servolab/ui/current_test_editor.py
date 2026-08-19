from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QRadioButton, QWidget

from ..config import CurrentAxis
from .widgets import make_double


class CurrentTestEditor(QGroupBox):
    """Compact selector for a single-axis dq current-loop experiment."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("dq 电流环测试", parent)
        form = QFormLayout(self)
        axis_widget = QWidget()
        axis_layout = QHBoxLayout(axis_widget)
        axis_layout.setContentsMargins(0, 0, 0, 0)
        self.axis_d = QRadioButton("d 轴（励磁）")
        self.axis_q = QRadioButton("q 轴（转矩）")
        axis_layout.addWidget(self.axis_d)
        axis_layout.addWidget(self.axis_q)
        self.lock_rotor = QCheckBox("锁定转子（推荐）")
        self.hint = QLabel()
        self.hint.setObjectName("CurrentTestHint")
        self.hint.setWordWrap(True)
        form.addRow("测试轴", axis_widget)
        form.addRow("机械状态", self.lock_rotor)
        form.addRow("本次目标", self.hint)
        self.axis_d.toggled.connect(self._selection_changed)
        self.axis_q.toggled.connect(self._selection_changed)
        self.lock_rotor.toggled.connect(self.changed)

    def load(self, axis: CurrentAxis, lock_rotor: bool) -> None:
        for widget in (self.axis_d, self.axis_q, self.lock_rotor):
            widget.blockSignals(True)
        self.axis_d.setChecked(axis == CurrentAxis.D)
        self.axis_q.setChecked(axis == CurrentAxis.Q)
        self.lock_rotor.setChecked(lock_rotor)
        for widget in (self.axis_d, self.axis_q, self.lock_rotor):
            widget.blockSignals(False)
        self.update_hint(axis)

    def selected_axis(self) -> CurrentAxis:
        return CurrentAxis.D if self.axis_d.isChecked() else CurrentAxis.Q

    def update_hint(self, axis: CurrentAxis | None = None) -> None:
        selected = axis or self.selected_axis()
        active = "Id" if selected == CurrentAxis.D else "Iq"
        inactive = "Iq" if selected == CurrentAxis.D else "Id"
        self.hint.setText(
            f"{active}* 由波形给定 · {inactive}* = 0.000 A（未激励轴自动置零）"
        )

    def _selection_changed(self, checked: bool) -> None:
        if checked:
            self.update_hint()
            self.changed.emit()


def add_inertia_group(owner, layout) -> None:
    group = QGroupBox("负载惯量变化")
    form = QFormLayout(group)
    owner.extra_inertia_enabled = QCheckBox("启用负载惯量阶跃")
    owner.extra_inertia = make_double(0, 0, 100, 8, 0.0001, " kg·m²")
    owner.inertia_time = make_double(1, 0, 1e4, 4, 0.1, " s")
    for label, widget in (
        ("", owner.extra_inertia_enabled),
        ("附加惯量", owner.extra_inertia),
        ("变化时刻", owner.inertia_time),
    ):
        form.addRow(label, widget)
    layout.addWidget(group)
