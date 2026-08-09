import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from .main_window import ServoLabWindow
from .theme import APP_STYLE


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ServoLab")
    app.setOrganizationName("ServoLab")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    font = QFont()
    font.setFamilies(
        ["DIN Alternate", "PingFang SC", "Microsoft YaHei UI", "Noto Sans CJK SC"]
    )
    app.setFont(font)
    window = ServoLabWindow()
    window.show()
    return app.exec_()
