from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .theme import PLOT_COLORS
from .widgets import ValueCard


def build_header(owner) -> QWidget:
    header = QFrame()
    header.setObjectName("Header")
    header.setFixedHeight(72)
    layout = QHBoxLayout(header)
    layout.setContentsMargins(18, 8, 18, 8)
    brand_box = QVBoxLayout()
    brand_box.setSpacing(0)
    brand = QLabel("SERVOLAB")
    brand.setObjectName("Brand")
    sub = QLabel("PMSM CONTROL TEACHING CONSOLE  /  01")
    sub.setObjectName("BrandSub")
    brand_box.addWidget(brand)
    brand_box.addWidget(sub)
    layout.addLayout(brand_box)
    layout.addSpacing(28)
    owner.run_button = QPushButton("▶  运行")
    owner.run_button.setObjectName("PrimaryButton")
    owner.run_button.setToolTip("运行或继续实时仿真（Space）")
    owner.pause_button = QPushButton("Ⅱ  暂停")
    owner.step_button = QPushButton("›|  单步")
    owner.reset_button = QPushButton("↺  复位")
    owner.offline_button = QPushButton("⚡  离线仿真")
    owner.compare_button = QPushButton("＋  保留对比")
    for button in (
        owner.run_button,
        owner.pause_button,
        owner.step_button,
        owner.reset_button,
        owner.offline_button,
        owner.compare_button,
    ):
        layout.addWidget(button)
    layout.addStretch()
    owner.open_button = QToolButton()
    owner.open_button.setText("打开")
    owner.save_button = QToolButton()
    owner.save_button.setText("保存")
    owner.export_button = QToolButton()
    owner.export_button.setText("导出")
    for button in (owner.open_button, owner.save_button, owner.export_button):
        layout.addWidget(button)
    _connect_header_actions(owner)
    return header


def _connect_header_actions(owner) -> None:
    owner.run_button.clicked.connect(owner.start_simulation)
    owner.pause_button.clicked.connect(owner.pause_simulation)
    owner.step_button.clicked.connect(owner.single_step)
    owner.reset_button.clicked.connect(owner.reset_simulation)
    owner.offline_button.clicked.connect(owner.run_offline)
    owner.compare_button.clicked.connect(owner.keep_comparison)
    owner.open_button.clicked.connect(owner.load_experiment)
    owner.save_button.clicked.connect(owner.save_experiment)
    owner.export_button.clicked.connect(owner.export_data_menu)


def build_right_panel(owner) -> QWidget:
    panel = QFrame()
    panel.setMinimumWidth(220)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 10, 10, 8)
    header = QHBoxLayout()
    label = QLabel("实时状态")
    label.setObjectName("SectionTitle")
    owner.run_state = QLabel("● STOPPED")
    owner.run_state.setObjectName("StatusStopped")
    header.addWidget(label)
    header.addStretch()
    header.addWidget(owner.run_state)
    layout.addLayout(header)
    _add_value_cards(owner, layout)
    layout.addWidget(_build_metric_group(owner))
    owner.clear_compare_button = QPushButton("清除对比曲线")
    owner.clear_compare_button.clicked.connect(owner.clear_comparisons)
    layout.addWidget(owner.clear_compare_button)
    layout.addStretch()
    return panel


def _add_value_cards(owner, layout) -> None:
    owner.time_card = ValueCard("SIM TIME", "s", PLOT_COLORS["muted"])
    owner.position_card = ValueCard("POSITION", "rad", PLOT_COLORS["feedback"])
    owner.speed_card = ValueCard("SPEED", "rpm", PLOT_COLORS["secondary"])
    owner.current_card = ValueCard("DQ CURRENT", "A", PLOT_COLORS["reference"])
    owner.torque_card = ValueCard("TORQUE", "N·m", PLOT_COLORS["disturbance"])
    for card in (
        owner.time_card,
        owner.position_card,
        owner.speed_card,
        owner.current_card,
        owner.torque_card,
    ):
        layout.addWidget(card)


def _build_metric_group(owner) -> QGroupBox:
    group = QGroupBox("本次实验指标")
    form = QFormLayout(group)
    owner.metric_peak = QLabel("—")
    owner.metric_rms = QLabel("—")
    owner.metric_settle = QLabel("—")
    owner.metric_samples = QLabel("0")
    owner.metric_peak_title = QLabel("位置峰值")
    owner.metric_rms_title = QLabel("位置误差 RMS")
    form.addRow(owner.metric_peak_title, owner.metric_peak)
    form.addRow(owner.metric_rms_title, owner.metric_rms)
    form.addRow("估计调节时间", owner.metric_settle)
    form.addRow("记录点数", owner.metric_samples)
    return group


def build_bottom_panel(owner) -> QWidget:
    owner.bottom_tabs = QTabWidget()
    owner.bottom_tabs.setMinimumHeight(145)
    owner.bottom_tabs.setMaximumHeight(340)
    owner.log_view = QPlainTextEdit()
    owner.log_view.setReadOnly(True)
    owner.log_view.setMaximumBlockCount(500)
    owner.log_tab_index = owner.bottom_tabs.addTab(owner.log_view, "运行日志")
    owner.custom_controller_page = QWidget()
    layout = QHBoxLayout(owner.custom_controller_page)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(18)
    summary = QVBoxLayout()
    summary.setSpacing(3)
    title = QLabel("独立编辑器")
    title.setObjectName("CustomEditorTitle")
    description = QLabel("在可自由缩放的单独窗口中编写、编译并启用 Python 控制策略。")
    description.setObjectName("CustomEditorDescription")
    owner.custom_summary_status = QLabel()
    for widget in (title, description, owner.custom_summary_status):
        summary.addWidget(widget)
    layout.addLayout(summary, 1)
    owner.open_custom_editor_button = QPushButton("打开控制器编辑器  ↗")
    owner.open_custom_editor_button.setObjectName("PrimaryButton")
    owner.open_custom_editor_button.setMinimumWidth(190)
    layout.addWidget(owner.open_custom_editor_button, 0, Qt.AlignVCenter)
    owner.custom_controller_tab_index = owner.bottom_tabs.addTab(
        owner.custom_controller_page, "自定义控制器"
    )
    return owner.bottom_tabs


def build_status_bar(owner) -> None:
    status = QStatusBar()
    status.setSizeGripEnabled(False)
    owner.status_message = QLabel("READY")
    owner.status_message.setObjectName("StatusStopped")
    owner.sample_status = QLabel("dt 200 μs  ·  plot 2 ms")
    status.addWidget(owner.status_message)
    status.addPermanentWidget(owner.sample_status)
    owner.setStatusBar(status)
