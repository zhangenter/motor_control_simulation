from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from ..config import FeedbackConfig, SpeedEstimatorMethod
from .widgets import make_double, make_int


class FeedbackEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, config: FeedbackConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 16)
        note = QLabel("测量链路：真实位置 → 编码器 → 速度估算 → 控制器。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #71858b; padding: 3px;")
        layout.addWidget(note)
        self._add_encoder_group(layout)
        self._add_estimator_group(layout)
        layout.addStretch()
        self.load_config(config)

    def _add_encoder_group(self, layout) -> None:
        group = QGroupBox("编码器")
        form = QFormLayout(group)
        self.encoder_noise = make_double(0, 0, 1000, 8, 0.00001, " rad")
        self.encoder_resolution = make_int(65536, 0, 100000000, " cnt/rev")
        self.encoder_delay = make_double(0, 0, 10, 6, 0.0001, " s")
        form.addRow("位置噪声 σ", self.encoder_noise)
        form.addRow("分辨率", self.encoder_resolution)
        form.addRow("采样延迟", self.encoder_delay)
        layout.addWidget(group)
        for widget in (self.encoder_noise, self.encoder_resolution, self.encoder_delay):
            widget.valueChanged.connect(self._emit_changed)

    def _add_estimator_group(self, layout) -> None:
        group = QGroupBox("速度估算")
        form = QFormLayout(group)
        self.estimator_method = QComboBox()
        self.estimator_method.addItems([method.value for method in SpeedEstimatorMethod])
        self.estimator_cutoff = make_double(50, 0.1, 10000, 2, 5, " Hz")
        self.pll_bandwidth = make_double(30, 0.1, 10000, 2, 5, " Hz")
        self.pll_damping = make_double(0.707, 0.1, 5, 3, 0.1)
        self.kalman_acceleration_noise = make_double(
            500, 0.001, 1e7, 3, 50, " rad/s²"
        )
        self.observer_bandwidth = make_double(30, 0.1, 10000, 2, 5, " Hz")
        self.observer_damping = make_double(1, 0.1, 5, 3, 0.1)
        self.estimator_hint = QLabel()
        self.estimator_hint.setWordWrap(True)
        self.estimator_hint.setStyleSheet("color: #71858b; padding: 4px 0;")
        form.addRow("估算方法", self.estimator_method)
        form.addRow("低通截止频率", self.estimator_cutoff)
        form.addRow("PLL 带宽", self.pll_bandwidth)
        form.addRow("PLL 阻尼比", self.pll_damping)
        form.addRow("加速度噪声 σ", self.kalman_acceleration_noise)
        form.addRow("观测器带宽", self.observer_bandwidth)
        form.addRow("观测器阻尼比", self.observer_damping)
        form.addRow(self.estimator_hint)
        layout.addWidget(group)
        self.estimator_form = form
        self.estimator_method.currentTextChanged.connect(self._method_changed)
        for widget in self._estimator_parameter_fields():
            widget.valueChanged.connect(self._emit_changed)

    def _method_changed(self, *_args) -> None:
        self._update_method_state()
        self._emit_changed()

    def _update_method_state(self) -> None:
        method = SpeedEstimatorMethod(self.estimator_method.currentText())
        visible = {
            SpeedEstimatorMethod.FILTERED_DIFFERENCE: (self.estimator_cutoff,),
            SpeedEstimatorMethod.PLL: (self.pll_bandwidth, self.pll_damping),
            SpeedEstimatorMethod.KALMAN: (self.kalman_acceleration_noise,),
            SpeedEstimatorMethod.STATE_OBSERVER: (
                self.observer_bandwidth,
                self.observer_damping,
            ),
        }.get(method, ())
        for field in self._estimator_parameter_fields():
            show = field in visible
            field.setEnabled(show)
            field.setVisible(show)
            label = self.estimator_form.labelForField(field)
            if label is not None:
                label.setVisible(show)
        hints = {
            SpeedEstimatorMethod.IDEAL: "直接使用模型真实速度，仅用于基准对照。",
            SpeedEstimatorMethod.DIFFERENCE: "由相邻编码器位置差分，能直接观察量化抖动。",
            SpeedEstimatorMethod.FILTERED_DIFFERENCE: "位置差分后使用一阶低通，是默认的真实反馈链路。",
            SpeedEstimatorMethod.PLL: "用相位误差锁定编码器位置，带宽决定跟随速度与抑噪能力。",
            SpeedEstimatorMethod.KALMAN: (
                "用位置/速度状态模型递推估算；测量噪声由编码器噪声和分辨率自动计算。"
            ),
            SpeedEstimatorMethod.STATE_OBSERVER: (
                "二阶位置/速度状态观测器，带宽和阻尼比共同决定观测动态。"
            ),
        }
        self.estimator_hint.setText(hints[method])

    def _estimator_parameter_fields(self):
        return (
            self.estimator_cutoff,
            self.pll_bandwidth,
            self.pll_damping,
            self.kalman_acceleration_noise,
            self.observer_bandwidth,
            self.observer_damping,
        )

    def _emit_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    def update_config(self, config: FeedbackConfig) -> None:
        config.encoder.noise_std = self.encoder_noise.value()
        config.encoder.resolution = self.encoder_resolution.value()
        config.encoder.delay = self.encoder_delay.value()
        config.speed_estimator.method = SpeedEstimatorMethod(self.estimator_method.currentText())
        config.speed_estimator.cutoff_frequency = self.estimator_cutoff.value()
        config.speed_estimator.pll_bandwidth = self.pll_bandwidth.value()
        config.speed_estimator.pll_damping = self.pll_damping.value()
        config.speed_estimator.kalman_acceleration_noise = self.kalman_acceleration_noise.value()
        config.speed_estimator.observer_bandwidth = self.observer_bandwidth.value()
        config.speed_estimator.observer_damping = self.observer_damping.value()

    def load_config(self, config: FeedbackConfig) -> None:
        self._loading = True
        self.encoder_noise.setValue(config.encoder.noise_std)
        self.encoder_resolution.setValue(config.encoder.resolution)
        self.encoder_delay.setValue(config.encoder.delay)
        self.estimator_method.setCurrentText(config.speed_estimator.method.value)
        self.estimator_cutoff.setValue(config.speed_estimator.cutoff_frequency)
        self.pll_bandwidth.setValue(config.speed_estimator.pll_bandwidth)
        self.pll_damping.setValue(config.speed_estimator.pll_damping)
        self.kalman_acceleration_noise.setValue(
            config.speed_estimator.kalman_acceleration_noise
        )
        self.observer_bandwidth.setValue(config.speed_estimator.observer_bandwidth)
        self.observer_damping.setValue(config.speed_estimator.observer_damping)
        self._update_method_state()
        self._loading = False
