APP_STYLE = r"""
QWidget {
    color: #d8e2e5;
    background: #101619;
    font-family: "DIN Alternate", "Microsoft YaHei UI", "PingFang SC";
    font-size: 12px;
}
QMainWindow, QDialog { background: #0b1012; }
QToolTip {
    color: #eaf7f5;
    background: #253036;
    border: 1px solid #4b6269;
    padding: 5px;
}
QFrame#Header {
    background: #111a1e;
    border-bottom: 1px solid #26353b;
}
QMenuBar {
    color: #aebfc3;
    background: #0c1316;
    border-bottom: 1px solid #243239;
    padding: 2px 10px;
}
QMenuBar::item { background: transparent; padding: 5px 12px; }
QMenuBar::item:selected { color: #e9f5f3; background: #1b2a2f; }
QMenu {
    color: #dce7e9;
    background: #121c20;
    border: 1px solid #34464d;
    padding: 6px;
}
QMenu::item { min-width: 180px; padding: 7px 28px 7px 12px; }
QMenu::item:selected { color: #0b1714; background: #45d6ad; }
QMenu::separator { height: 1px; background: #2a3a40; margin: 5px 8px; }
QLabel#Brand {
    color: #f2f7f8;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#BrandSub { color: #6f858d; font-size: 10px; letter-spacing: 1px; }
QLabel#SectionTitle {
    color: #91a7ad;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 5px 0;
}
QLabel#DialogTitle { color: #edf8f6; font-size: 20px; font-weight: 700; }
QFrame#TuningHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #142722, stop:1 #111a1e);
    border: 1px solid #2b4a42;
    border-left: 3px solid #45d6ad;
}
QLabel#TuningEyebrow { color: #52d8b3; font-size: 9px; font-weight: 700; letter-spacing: 2px; }
QFrame#TuningHeader QLabel { background: transparent; }
QLabel#TuningDescription { color: #84989e; background: transparent; }
QLabel#TuningContext {
    color: #8adfc6;
    background: #162621;
    border: 1px solid #2b4a42;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 10px;
}
QFrame#TuningPanel { background: #10191c; border: 1px solid #293a40; }
QFrame#TuningPanel QLabel { background: transparent; }
QLabel#TuningPanelTitle { color: #e2eeee; font-size: 14px; font-weight: 700; }
QLabel#TuningFormula {
    color: #d7b66d;
    background: #171b19;
    border-left: 2px solid #a9823e;
    padding: 7px 9px;
    font-family: "Menlo", "Consolas";
}
QLabel#TuningHint { color: #6f858c; background: transparent; }
QLabel#CurrentTestHint {
    color: #8adfc6;
    background: #111d1a;
    border-left: 2px solid #45d6ad;
    padding: 6px 8px;
}
QFrame#TuningResults { background: #0c1316; border: 1px solid #293a40; }
QFrame#TuningResultCard { background: #142025; border: 1px solid #263b42; }
QFrame#TuningResults QLabel { background: transparent; }
QLabel#TuningGainName { color: #6f858c; font-size: 9px; font-weight: 700; letter-spacing: 1px; }
QLabel#TuningGainValue {
    color: #55ddb7;
    font-size: 18px;
    font-weight: 700;
    font-family: "Menlo", "Consolas";
}
QLabel#CustomEditorTitle { color: #e4edef; font-size: 14px; font-weight: 700; }
QLabel#CustomEditorDescription { color: #7f9399; }
QLabel#CustomEditorWarning { color: #d0a05b; padding: 4px 0; }
QLabel#CodeFileName { color: #9fb1b6; font-weight: 700; }
QLabel#CodeShortcut { color: #64787e; font-size: 10px; }
QLabel#StatusRunning { color: #45e1b4; font-weight: 700; }
QLabel#StatusPaused { color: #e3b45d; font-weight: 700; }
QLabel#StatusStopped { color: #73868c; font-weight: 700; }
QLabel#ValueLarge { color: #edf8f6; font-size: 23px; font-weight: 600; }
QLabel#ValueUnit { color: #667a80; font-size: 10px; }
QFrame#ValueCard {
    background: #131d21;
    border: 1px solid #233239;
    border-radius: 3px;
}
QFrame#ValueCard:hover { border-color: #3b5b63; }
QFrame#CodeEditorFrame { background: #0a0f11; border: 1px solid #2a3a40; }
QFrame#CodeEditorBar { background: #151f23; border-bottom: 1px solid #2a3a40; }
QFrame#ControllerGeneratorBar {
    background: #111b1e;
    border-top: 1px solid #223238;
    border-bottom: 1px solid #2a3a40;
}
QLabel#GeneratorTitle { color: #45d6ad; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#GeneratorContext { color: #dce8e9; font-weight: 700; }
QPushButton#GenerateButton { color: #8ce6cc; border-color: #315c52; padding: 5px 10px; }
QPushButton#GenerateButton:hover { background: #1d3731; border-color: #45bfa0; }
QPlainTextEdit#CustomCodeEditor { border: none; background: #0b1114; }
QPushButton, QToolButton {
    color: #cbd8db;
    background: #192328;
    border: 1px solid #2b3a40;
    border-radius: 3px;
    padding: 7px 11px;
}
QPushButton:hover, QToolButton:hover { background: #223138; border-color: #45616a; }
QPushButton:pressed, QToolButton:pressed { background: #0d1417; }
QPushButton:checked, QToolButton:checked {
    color: #081513;
    background: #45d6ad;
    border-color: #6ceac7;
}
QPushButton#PrimaryButton {
    color: #071310;
    background: #45d6ad;
    border-color: #62e5c0;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover { background: #60e5c0; }
QPushButton#DangerButton { color: #ffb9a8; border-color: #624039; }
QPushButton:disabled, QToolButton:disabled { color: #526166; background: #141b1e; }
QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    color: #e2ecee;
    background: #0d1417;
    border: 1px solid #29383e;
    border-radius: 2px;
    padding: 5px 7px;
    selection-background-color: #327c70;
}
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #45bfa0;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #162126;
    border: 1px solid #34474e;
    selection-background-color: #27584f;
}
QCheckBox { spacing: 7px; color: #bdcace; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #3b4d54; background: #0c1215; }
QCheckBox::indicator:checked { background: #43cda7; border: 3px solid #152125; }
QGroupBox {
    color: #91a7ad;
    border: 1px solid #25343a;
    border-radius: 3px;
    margin-top: 13px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 5px; }
QTabWidget::pane { border: 1px solid #26363c; background: #101719; }
QTabBar::tab {
    color: #73888e;
    background: #101719;
    padding: 8px 13px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #dce8e9; border-bottom-color: #42cda6; }
QTabBar::tab:hover { color: #b9c8cb; }
QScrollArea { border: none; }
QScrollBar:vertical { width: 8px; background: #0c1214; }
QScrollBar::handle:vertical { background: #34464c; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #26343a; width: 1px; height: 1px; }
QProgressBar {
    color: #dce8e8;
    background: #121b1e;
    border: 1px solid #26363c;
    text-align: center;
}
QProgressBar::chunk { background: #42cba5; }
QTableWidget { gridline-color: #243239; alternate-background-color: #141e22; }
QHeaderView::section { background: #182328; color: #8fa4aa; border: none; padding: 6px; }
"""


PLOT_COLORS = {
    "reference": "#e5b85c",
    "feedback": "#51d9b1",
    "secondary": "#5fb8e8",
    "error": "#ef756f",
    "disturbance": "#bd83e6",
    "muted": "#839399",
}
