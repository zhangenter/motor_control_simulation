from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QSyntaxHighlighter
from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..config import ExperimentConfig
from ..control import CustomControllerError
from ..services import (
    ControllerGenerationOptions,
    ControllerSourceService,
    SimulationSession,
    generate_custom_controller_code,
)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        keyword_format = _text_format("#e5b85c", bold=True)
        for word in (
            "def", "return", "if", "else", "elif", "for", "while", "in", "and", "or",
            "not", "True", "False", "None", "try", "except", "raise", "class", "from", "import",
        ):
            self.rules.append((re.compile(rf"\b{word}\b"), keyword_format))
        self.rules.append((re.compile(r"\b\d+(?:\.\d+)?\b"), _text_format("#6fbee8")))
        self.rules.append((re.compile(r"#.*$"), _text_format("#60777e")))
        self.rules.append((re.compile(r"(['\"])(?:(?!\1).)*\1"), _text_format("#72d5a8")))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for pattern, text_format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)


def _text_format(color: str, bold: bool = False) -> QTextCharFormat:
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Bold)
    return text_format


class CustomControllerDialog(QDialog):
    def __init__(self, initial_code: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CustomControllerDialog")
        self.setWindowTitle("自定义控制器 · ServoLab")
        self.setModal(False)
        self.resize(1080, 720)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(self._build_header())
        layout.addWidget(self._build_editor(initial_code), 1)
        layout.addLayout(self._build_footer())
        self._install_shortcuts()

    @staticmethod
    def _build_header() -> QHBoxLayout:
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(1)
        eyebrow = QLabel("CUSTOM CONTROL / PYTHON")
        eyebrow.setObjectName("SectionTitle")
        title = QLabel("控制器代码编辑器")
        title.setObjectName("DialogTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header.addLayout(heading)
        header.addStretch()
        warning = QLabel("独立进程  ·  40 ms 超时  ·  仅运行可信代码")
        warning.setObjectName("CustomEditorWarning")
        header.addWidget(warning, 0, Qt.AlignBottom)
        return header

    def _build_editor(self, initial_code: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CodeEditorFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self._build_editor_bar())
        layout.addWidget(self._build_generator_bar())
        self.code_editor = QPlainTextEdit(initial_code)
        self.code_editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code_editor.setObjectName("CustomCodeEditor")
        self.code_editor.setStyleSheet(
            'font-family: "SF Mono", "Cascadia Code", "JetBrains Mono", monospace; '
            "font-size: 13px; padding: 12px;"
        )
        self.highlighter = PythonHighlighter(self.code_editor.document())
        self.code_editor.document().setModified(False)
        layout.addWidget(self.code_editor, 1)
        return frame

    def _build_editor_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("CodeEditorBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(11, 7, 11, 7)
        self.file_label = QLabel()
        self.file_label.setObjectName("CodeFileName")
        self.open_button = QPushButton("打开代码")
        self.save_button = QPushButton("保存代码")
        layout.addWidget(self.file_label)
        layout.addStretch()
        layout.addWidget(self.open_button)
        layout.addWidget(self.save_button)
        return bar

    def _build_generator_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("ControllerGeneratorBar")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(11, 8, 11, 9)
        layout.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("AUTO SYNTHESIS")
        title.setObjectName("GeneratorTitle")
        self.generator_context = QLabel()
        self.generator_context.setObjectName("GeneratorContext")
        self.generate_button = QPushButton("按当前配置生成")
        self.generate_button.setObjectName("GenerateButton")
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self.generator_context)
        header.addStretch()
        header.addWidget(self.generate_button)
        layout.addLayout(header)
        layout.addLayout(self._build_generator_options())
        return bar

    def _build_generator_options(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(18)
        label = QLabel("生成选项")
        label.setObjectName("CodeShortcut")
        self.generator_feedforward = QCheckBox("参考前馈 Kff")
        self.generator_back_emf = QCheckBox("反电动势补偿")
        self.generator_decoupling = QCheckBox("dq 解耦")
        self.generator_friction = QCheckBox("黏性摩擦补偿")
        self.generator_anti_windup = QCheckBox("抗积分饱和")
        self.generator_back_emf.setChecked(True)
        self.generator_decoupling.setChecked(True)
        self.generator_anti_windup.setChecked(True)
        layout.addWidget(label)
        for checkbox in self.generation_checkboxes():
            layout.addWidget(checkbox)
        layout.addStretch()
        return layout

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(9)
        self.status_label = QLabel()
        footer.addWidget(self.status_label)
        footer.addStretch()
        self.api_button = QPushButton("状态 API")
        self.enable_checkbox = QCheckBox("接管控制输出")
        self.enable_checkbox.setEnabled(False)
        self.stop_button = QPushButton("停止控制器")
        self.stop_button.setObjectName("DangerButton")
        self.compile_button = QPushButton("编译并启动")
        self.compile_button.setObjectName("PrimaryButton")
        self.compile_button.setMinimumWidth(140)
        footer.addWidget(self.api_button)
        footer.addWidget(self.enable_checkbox)
        footer.addWidget(self.stop_button)
        footer.addWidget(self.compile_button)
        return footer

    def _install_shortcuts(self) -> None:
        compile_action = QAction(self)
        compile_action.setShortcut(QKeySequence("Ctrl+Return"))
        compile_action.triggered.connect(self.compile_button.click)
        self.addAction(compile_action)
        save_action = QAction(self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_button.click)
        self.addAction(save_action)

    def generation_checkboxes(self):
        return (
            self.generator_feedforward,
            self.generator_back_emf,
            self.generator_decoupling,
            self.generator_friction,
            self.generator_anti_windup,
        )

    def generation_options(self) -> ControllerGenerationOptions:
        return ControllerGenerationOptions(
            reference_feedforward=self.generator_feedforward.isChecked(),
            back_emf_compensation=self.generator_back_emf.isChecked(),
            dq_decoupling=self.generator_decoupling.isChecked(),
            friction_compensation=self.generator_friction.isChecked(),
            anti_windup=self.generator_anti_windup.isChecked(),
        )

    def show_editor(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.code_editor.setFocus()

    def set_context(self, config: ExperimentConfig) -> None:
        axis = (
            f" / {config.command.current_axis.value} 轴"
            if config.control.mode.value == "电流单环"
            else ""
        )
        self.generator_context.setText(
            f"{config.control.mode.value}  →  {config.command.reference_type.value}{axis}"
        )
        self.generator_context.setToolTip("参数取自主界面当前 PID 与电机配置")

    def set_file_label(self, path: Path | None) -> None:
        name = path.name if path else "controller.py"
        unsaved = "  • 未保存" if self.code_editor.document().isModified() else ""
        self.file_label.setText(f"●  {name}{unsaved}")
        self.file_label.setToolTip(str(path) if path else "尚未保存为文件")


class CustomControllerManager:
    STATUS_STYLES = {
        "idle": ("●  NOT RUNNING", "等待编译", "#73868c"),
        "modified": ("●  EDITED", "代码已修改，等待编译", "#e3b45d"),
        "modified_running": ("●  EDITED / PROCESS RUNNING", "当前进程仍使用上次编译的代码", "#e3b45d"),
        "ready": ("●  PROCESS READY", "已编译，尚未接管控制输出", "#6fbee8"),
        "active": ("●  OUTPUT ACTIVE", "自定义控制器正在接管输出", "#45e1b4"),
        "error": ("●  COMPILE ERROR", "编译失败，请修改代码后重试", "#ef756f"),
    }

    def __init__(
        self,
        parent,
        dialog: CustomControllerDialog,
        session: SimulationSession,
        summary_label: QLabel,
        sync_config: Callable[[], None],
        log: Callable[[str], None],
        pause: Callable[[], None],
    ):
        self.parent = parent
        self.dialog = dialog
        self.session = session
        self.summary_label = summary_label
        self.sync_config = sync_config
        self.log = log
        self.pause = pause
        self.source_path: Path | None = None
        self.needs_compile = False
        self._connect_actions()
        self.dialog.set_file_label(None)
        self.refresh_status()

    def _connect_actions(self) -> None:
        self.dialog.generate_button.clicked.connect(self.generate)
        self.dialog.open_button.clicked.connect(self.open_source)
        self.dialog.save_button.clicked.connect(self.save_source)
        self.dialog.compile_button.clicked.connect(self.compile)
        self.dialog.stop_button.clicked.connect(self.stop)
        self.dialog.enable_checkbox.toggled.connect(self.toggle)
        self.dialog.api_button.clicked.connect(self.show_api)
        self.dialog.code_editor.document().modificationChanged.connect(self.mark_dirty)

    def show_editor(self) -> None:
        self.refresh_context()
        self.dialog.show_editor()

    def generate(self) -> None:
        if not self.confirm_replace():
            return
        self.sync_config()
        config = self.session.config
        source = generate_custom_controller_code(
            config.control.mode,
            config.command.reference_type,
            config.control,
            config.motor,
            self.dialog.generation_options(),
            config.command.current_axis,
        )
        self.dialog.code_editor.setPlainText(source)
        self.source_path = None
        self.needs_compile = True
        self.dialog.code_editor.document().setModified(True)
        self.dialog.set_file_label(None)
        self.refresh_status()
        self.dialog.code_editor.setFocus()
        self.refresh_context()
        self.log(
            f"已根据 {config.control.mode.value} / "
            f"{config.command.reference_type.value} 生成自定义控制器。"
        )

    def open_source(self) -> None:
        if not self.confirm_replace():
            return
        path, _ = QFileDialog.getOpenFileName(
            self.parent,
            "打开自定义控制器代码",
            "",
            "Python 代码 (*.py);;所有文件 (*)",
        )
        if not path:
            return
        try:
            source = ControllerSourceService.load(path)
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(self.parent, "代码打开失败", str(exc))
            return
        self.dialog.code_editor.setPlainText(source)
        self.source_path = Path(path)
        self.needs_compile = True
        self.dialog.code_editor.document().setModified(False)
        self.dialog.set_file_label(self.source_path)
        self.refresh_status()
        self.dialog.code_editor.setFocus()
        self.log(f"已打开自定义控制器代码：{path}")

    def save_source(self) -> bool:
        path = self.source_path
        if path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self.parent,
                "保存自定义控制器代码",
                "custom_controller.py",
                "Python 代码 (*.py)",
            )
            if not selected:
                return False
            path = Path(selected)
        try:
            self.source_path = ControllerSourceService.save(
                path,
                self.dialog.code_editor.toPlainText(),
            )
        except OSError as exc:
            QMessageBox.critical(self.parent, "代码保存失败", str(exc))
            return False
        self.dialog.code_editor.document().setModified(False)
        self.dialog.set_file_label(self.source_path)
        self.log(f"自定义控制器代码已保存：{self.source_path}")
        return True

    def confirm_replace(self) -> bool:
        if not self.dialog.code_editor.document().isModified():
            return True
        choice = QMessageBox.warning(
            self.parent,
            "代码尚未保存",
            "当前代码有未保存的修改，是否先保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Save:
            return self.save_source()
        return choice == QMessageBox.Discard

    def compile(self) -> None:
        try:
            self.session.start_custom_controller(self.dialog.code_editor.toPlainText())
        except CustomControllerError as exc:
            self.dialog.enable_checkbox.setChecked(False)
            self.dialog.enable_checkbox.setEnabled(False)
            self._set_status("error")
            QMessageBox.critical(self.parent, "自定义控制器编译失败", str(exc))
            self.log(f"自定义控制器错误：{exc}")
            return
        self.needs_compile = False
        self.dialog.enable_checkbox.setEnabled(True)
        self.dialog.enable_checkbox.setChecked(True)
        self.refresh_status()
        self.log("自定义控制器编译成功并已接管控制输出。")

    def stop(self) -> None:
        self.dialog.enable_checkbox.setChecked(False)
        self.dialog.enable_checkbox.setEnabled(False)
        self.session.stop_custom_controller()
        self.refresh_status()
        self.log("自定义控制器进程已停止，恢复内置控制器。")

    def toggle(self, enabled: bool) -> None:
        self.session.set_custom_controller_enabled(enabled)
        self.refresh_status()
        if self.session.simulation.use_custom_controller:
            self.log("控制输出已切换到自定义控制器。")

    def mark_dirty(self, modified: bool) -> None:
        if modified:
            self.needs_compile = True
        self.dialog.set_file_label(self.source_path)
        self.refresh_status()

    def refresh_context(self) -> None:
        self.dialog.set_context(self.session.config)

    def refresh_status(self) -> None:
        runtime = self.session.custom_controller
        if self.needs_compile:
            state = "modified_running" if runtime.running else "modified"
        elif runtime.running:
            state = "active" if self.session.simulation.use_custom_controller else "ready"
        else:
            state = "idle"
        self._set_status(state)

    def _set_status(self, state: str) -> None:
        status, summary, color = self.STATUS_STYLES[state]
        self.dialog.status_label.setText(status)
        self.dialog.status_label.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.summary_label.setText(summary)
        self.summary_label.setStyleSheet(f"color: {color};")

    def handle_error(self, error: Exception) -> None:
        self.pause()
        self.session.simulation.use_custom_controller = False
        self.dialog.enable_checkbox.blockSignals(True)
        self.dialog.enable_checkbox.setChecked(False)
        self.dialog.enable_checkbox.blockSignals(False)
        self.dialog.enable_checkbox.setEnabled(False)
        self.session.custom_controller.stop()
        self._set_status("error")
        self.log(f"自定义控制器已停止：{error}")
        QMessageBox.critical(self.parent, "自定义控制器运行错误", str(error))

    def show_api(self) -> None:
        QMessageBox.information(
            self.parent,
            "自定义控制器 API",
            "state：id, iq, theta, omega (rpm), torque, t\n"
            "reference：command, user_input, position, speed (rpm), current\n"
            "params：跨控制周期保留的字典\n"
            "dt：控制周期，单位 s\n\n"
            '返回 {"vd": ..., "vq": ...}，或仅返回 vq 数值。\n'
            "math 模块已预载；不允许 import。",
        )
