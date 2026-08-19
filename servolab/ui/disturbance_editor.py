from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import DisturbanceConfig
from .widgets import make_double, make_int


class DisturbanceEditor(QWidget):
    """Tabbed editor for mechanical, load, and electrical disturbances."""

    changed = pyqtSignal()

    def __init__(self, config: DisturbanceConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel("干扰按作用位置分类；各开关可独立启用并叠加。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #71858b; padding: 4px 8px;")
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_mechanical_tab(), "机械")
        self.tabs.addTab(self._build_load_tab(), "负载")
        self.tabs.addTab(self._build_electrical_tab(), "电气")
        layout.addWidget(self.tabs)
        self._connect_fields()
        self.load_config(config)

    def _build_mechanical_tab(self) -> QWidget:
        page, layout = _page()
        cogging = QGroupBox("齿槽转矩")
        form = QFormLayout(cogging)
        self.cogging_enabled = QCheckBox("启用齿槽效应")
        self.cogging_amplitude = make_double(0.02, 0, 1000, 5, 0.01, " N·m")
        self.cogging_harmonic = make_int(6, 1, 100)
        self.cogging_phase = make_double(0, -360, 360, 2, 5, "°")
        _add_rows(form, (
            ("", self.cogging_enabled), ("幅值", self.cogging_amplitude),
            ("空间谐波", self.cogging_harmonic), ("相位", self.cogging_phase),
        ))
        layout.addWidget(cogging)

        friction = QGroupBox("摩擦模型")
        form = QFormLayout(friction)
        self.friction_enabled = QCheckBox("启用 Stribeck 复合摩擦")
        self.static_friction = make_double(0.04, 0, 1000, 5, 0.01, " N·m")
        self.coulomb_friction = make_double(0.025, 0, 1000, 5, 0.01, " N·m")
        self.friction_viscous = make_double(0.0002, 0, 100, 7, 0.0001)
        self.stribeck_velocity = make_double(4.77464829, 0.0001, 1e6, 5, 1.0, " rpm")
        _add_rows(form, (
            ("", self.friction_enabled), ("最大静摩擦", self.static_friction),
            ("库仑摩擦", self.coulomb_friction),
            ("黏性摩擦系数", self.friction_viscous),
            ("Stribeck 速度", self.stribeck_velocity),
        ))
        layout.addWidget(friction)
        layout.addStretch()
        return page

    def _build_load_tab(self) -> QWidget:
        page, layout = _page()
        group = QGroupBox("组合负载与惯量")
        form = QFormLayout(group)
        self.load_enabled = QCheckBox("启用负载转矩干扰")
        self.load_constant = make_double(0, -1000, 1000, 5, 0.01, " N·m")
        self.load_step = make_double(0.08, -1000, 1000, 5, 0.01, " N·m")
        self.load_step_time = make_double(1.5, 0, 1e4, 4, 0.1, " s")
        self.load_sine_amp = make_double(0, 0, 1000, 5, 0.01, " N·m")
        self.load_sine_freq = make_double(1, 0, 1e4, 4, 0.1, " Hz")
        self.load_noise = make_double(0, 0, 1000, 6, 0.001, " N·m")
        self.extra_inertia_enabled = QCheckBox("启用负载惯量阶跃")
        self.extra_inertia = make_double(0, 0, 100, 8, 0.0001, " kg·m²")
        self.inertia_time = make_double(1, 0, 1e4, 4, 0.1, " s")
        _add_rows(form, (
            ("", self.load_enabled), ("恒定转矩", self.load_constant),
            ("转矩阶跃", self.load_step), ("阶跃时刻", self.load_step_time),
            ("正弦幅值", self.load_sine_amp), ("正弦频率", self.load_sine_freq),
            ("随机噪声 σ", self.load_noise), ("", self.extra_inertia_enabled),
            ("附加惯量", self.extra_inertia), ("惯量变化时刻", self.inertia_time),
        ))
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _build_electrical_tab(self) -> QWidget:
        page, layout = _page()
        inverter = QGroupBox("逆变器开关与死区")
        form = QFormLayout(inverter)
        self.pwm_enabled = QCheckBox("启用 PWM 等效开关纹波")
        self.pwm_frequency = make_double(10000, 1, 1e7, 1, 1000, " Hz")
        self.pwm_ripple = make_double(2, 0, 100, 3, 0.5, " %")
        self.dead_time_enabled = QCheckBox("启用死区压降")
        self.dead_time_us = make_double(2, 0, 1000, 3, 0.5, " μs")
        _add_rows(form, (
            ("", self.pwm_enabled), ("开关频率", self.pwm_frequency),
            ("等效纹波幅值", self.pwm_ripple), ("", self.dead_time_enabled),
            ("死区时间", self.dead_time_us),
        ))
        layout.addWidget(inverter)

        supply = QGroupBox("直流母线波动")
        form = QFormLayout(supply)
        self.bus_voltage_enabled = QCheckBox("启用母线电压波动")
        self.bus_offset = make_double(0, -95, 200, 3, 1, " %")
        self.bus_ripple = make_double(5, 0, 100, 3, 0.5, " %")
        self.bus_frequency = make_double(100, 0, 1e6, 2, 10, " Hz")
        _add_rows(form, (
            ("", self.bus_voltage_enabled), ("直流偏差", self.bus_offset),
            ("纹波幅值", self.bus_ripple), ("纹波频率", self.bus_frequency),
        ))
        layout.addWidget(supply)

        back_emf = QGroupBox("反电动势非正弦谐波")
        form = QFormLayout(back_emf)
        self.back_emf_enabled = QCheckBox("启用反电动势谐波")
        self.back_emf_amplitude = make_double(5, 0, 100, 3, 0.5, " %")
        self.back_emf_order = make_int(6, 1, 100)
        self.back_emf_phase = make_double(0, -360, 360, 2, 5, "°")
        _add_rows(form, (
            ("", self.back_emf_enabled), ("相对基波幅值", self.back_emf_amplitude),
            ("电角谐波次数", self.back_emf_order), ("相位", self.back_emf_phase),
        ))
        layout.addWidget(back_emf)
        layout.addStretch()
        return page

    def _connect_fields(self) -> None:
        for check in self._checks():
            check.toggled.connect(self._emit_changed)
        for field in self._fields():
            field.valueChanged.connect(self._emit_changed)

    def _emit_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def update_config(self, config: DisturbanceConfig) -> None:
        for name, check in zip(_CHECK_NAMES, self._checks()):
            setattr(config, name, check.isChecked())
        for name, field in zip(_FIELD_NAMES, self._fields()):
            setattr(config, name, field.value())

    def load_config(self, config: DisturbanceConfig) -> None:
        self._loading = True
        for name, check in zip(_CHECK_NAMES, self._checks()):
            check.setChecked(getattr(config, name))
        for name, field in zip(_FIELD_NAMES, self._fields()):
            field.setValue(getattr(config, name))
        self._loading = False

    def _checks(self):
        return (
            self.cogging_enabled, self.friction_enabled, self.load_enabled,
            self.extra_inertia_enabled, self.pwm_enabled, self.dead_time_enabled,
            self.bus_voltage_enabled, self.back_emf_enabled,
        )

    def _fields(self):
        return (
            self.cogging_amplitude, self.cogging_harmonic, self.cogging_phase,
            self.static_friction, self.coulomb_friction, self.friction_viscous,
            self.stribeck_velocity, self.load_constant, self.load_step, self.load_step_time,
            self.load_sine_amp, self.load_sine_freq, self.load_noise,
            self.extra_inertia, self.inertia_time, self.pwm_frequency, self.pwm_ripple,
            self.dead_time_us, self.bus_offset, self.bus_ripple, self.bus_frequency,
            self.back_emf_amplitude, self.back_emf_order, self.back_emf_phase,
        )


_CHECK_NAMES = (
    "cogging_enabled", "friction_enabled", "load_enabled", "extra_inertia_enabled",
    "pwm_enabled", "dead_time_enabled", "bus_voltage_enabled", "back_emf_enabled",
)

_FIELD_NAMES = (
    "cogging_amplitude", "cogging_harmonic", "cogging_phase_deg", "static_friction",
    "coulomb_friction", "viscous_friction", "stribeck_velocity", "load_constant",
    "load_step", "load_step_time", "load_sine_amplitude", "load_sine_frequency",
    "load_noise_std", "extra_inertia", "inertia_step_time", "pwm_switching_frequency",
    "pwm_ripple_percent", "dead_time_us", "bus_voltage_offset_percent",
    "bus_voltage_ripple_percent", "bus_voltage_ripple_frequency",
    "back_emf_harmonic_percent", "back_emf_harmonic_order", "back_emf_phase_deg",
)


def _page() -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(8, 8, 8, 12)
    return page, layout


def _add_rows(form: QFormLayout, rows) -> None:
    for label, widget in rows:
        if label:
            form.addRow(label, widget)
        else:
            form.addRow(widget)
