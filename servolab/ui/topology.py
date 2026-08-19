from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from ..config import CurrentAxis, LoopMode, ReferenceType, has_position_outer_loop


class TopologyWidget(QWidget):
    """Compact, custom-painted view of the currently active loop topology."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = LoopMode.CASCADE
        self.reference_type = ReferenceType.POSITION
        self.current_axis = CurrentAxis.Q
        self.setMinimumHeight(100)
        self.setMaximumHeight(112)

    def set_mode(self, mode: LoopMode) -> None:
        self.mode = mode
        self.update()

    def set_reference_type(self, reference_type: ReferenceType) -> None:
        self.reference_type = reference_type
        self.update()

    def set_current_axis(self, current_axis: CurrentAxis) -> None:
        self.current_axis = current_axis
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
        nodes = self._nodes()
        left, right = 16.0, self.width() - 16.0
        gap = 13.0
        node_width = (right - left - gap * (len(nodes) - 1)) / len(nodes)
        body_font = QFont(self.font())
        body_font.setPixelSize(11)
        painter.setFont(body_font)
        for index, label in enumerate(nodes):
            self._paint_node(painter, index, label, len(nodes), left, gap, node_width)

    def _nodes(self) -> list[str]:
        current_label = "d轴 PI" if self.mode == LoopMode.CURRENT and self.current_axis == CurrentAxis.D else "q轴 PI"
        mode_nodes = {
            LoopMode.CURRENT: [current_label, "PMSM"],
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
            ReferenceType.CURRENT: "Id 指令" if self.current_axis == CurrentAxis.D else "Iq 指令",
        }
        nodes = [input_labels[self.reference_type]]
        if self.reference_type == ReferenceType.SPEED and has_position_outer_loop(self.mode):
            nodes.append("积分 ∫")
        return nodes + mode_nodes[self.mode]

    @staticmethod
    def _paint_node(painter, index, label, count, left, gap, node_width) -> None:
        x = left + index * (node_width + gap)
        rect = QRectF(x, 39.0, node_width, 43.0)
        fill = QColor("#173029") if index not in (0, count - 1) else QColor("#172329")
        edge = QColor("#45c9a5") if index not in (0, count - 1) else QColor("#3c555e")
        painter.setBrush(fill)
        painter.setPen(QPen(edge, 1))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QColor("#dbe8e8"))
        painter.drawText(rect, Qt.AlignCenter, label)
        if index < count - 1:
            x1, x2 = rect.right() + 2, rect.right() + gap - 2
            center_y = rect.center().y()
            painter.setPen(QPen(QColor("#5a767d"), 1.2))
            painter.drawLine(int(x1), int(center_y), int(x2), int(center_y))
            painter.drawLine(int(x2 - 4), int(center_y - 3), int(x2), int(center_y))
            painter.drawLine(int(x2 - 4), int(center_y + 3), int(x2), int(center_y))
