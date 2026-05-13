"""Shared frameless dialog helpers."""

from PyQt5.QtWidgets import QDialog
from PyQt5.QtCore import Qt, QPoint, QRectF
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPainterPath


class FramelessRoundedDialog(QDialog):
    """Frameless dialog with rounded background and title-area dragging."""

    def __init__(self, bg_color: str, radius: int = 16, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(bg_color)
        self._radius = radius
        self._dragging = False
        self._drag_start = QPoint()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            self._radius, self._radius)
        painter.fillPath(path, self._bg_color)
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.pos().y() <= 52:
            self._dragging = True
            self._drag_start = event.globalPos() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self.move(event.globalPos() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        super().mouseReleaseEvent(event)
