"""
小地图区域选择器

透明悬浮窗，让用户通过拖动和缩放选择游戏中小地图的位置和大小。
参考 Game-Map-Tracker 的可视化选择器设计。
"""

import logging
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPainterPath,
    QMouseEvent, QWheelEvent, QKeyEvent
)

logger = logging.getLogger(__name__)


class MinimapSelector(QWidget):
    """
    小地图区域选择器

    一个半透明的悬浮窗口，用户可以:
    - 拖动选择小地图位置
    - 滚轮调整大小
    - Enter 确认选择
    - Escape 取消

    选择结果以 {"x", "y", "width", "height"} 字典形式返回。
    """

    # 信号
    selection_confirmed = pyqtSignal(dict)  # {"x", "y", "width", "height"}
    selection_cancelled = pyqtSignal()

    # 大小限制
    MIN_SIZE = 80
    MAX_SIZE = 500
    SIZE_STEP = 10

    def __init__(self, parent=None,
                 initial_x: int = 100, initial_y: int = 100,
                 initial_size: int = 200):
        super().__init__(parent)

        # 位置和大小
        self._sel_x = initial_x
        self._sel_y = initial_y
        self._sel_size = initial_size

        # 拖动状态
        self._dragging = False
        self._drag_start = QPoint()

        # 窗口设置
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # 覆盖全屏
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setGeometry(geo)

        self.setCursor(Qt.CrossCursor)

        logger.info("MinimapSelector opened (pos=%d,%d size=%d)",
                     initial_x, initial_y, initial_size)

    @property
    def selection(self) -> dict:
        """获取当前选择区域"""
        return {
            "x": self._sel_x,
            "y": self._sel_y,
            "width": self._sel_size,
            "height": self._sel_size
        }

    # ==================== Painting ====================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 半透明遮罩覆盖整个屏幕
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # 清除选择区域的遮罩 (让选择区域透明)
        sel_rect = QRect(self._sel_x, self._sel_y, self._sel_size, self._sel_size)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(sel_rect, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # 绘制选择框 - 圆形边框 (匹配小地图圆形)
        center_x = self._sel_x + self._sel_size // 2
        center_y = self._sel_y + self._sel_size // 2
        radius = self._sel_size // 2

        # 外圈 - 主边框
        pen = QPen(QColor(102, 126, 234, 220), 3)  # 蓝紫色 #667eea
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(center_x, center_y), radius, radius)

        # 十字准星
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        pen.setColor(QColor(102, 126, 234, 150))
        painter.setPen(pen)
        cross_len = radius - 5
        painter.drawLine(center_x - cross_len, center_y,
                         center_x + cross_len, center_y)
        painter.drawLine(center_x, center_y - cross_len,
                         center_x, center_y + cross_len)

        # 中心点
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(102, 126, 234, 200))
        painter.drawEllipse(QPoint(center_x, center_y), 4, 4)

        # 信息文字
        painter.setPen(QColor(255, 255, 255, 220))
        font = QFont("Arial", 12, QFont.Bold)
        painter.setFont(font)

        info_y = self._sel_y - 30 if self._sel_y > 60 else self._sel_y + self._sel_size + 25
        painter.drawText(
            self._sel_x, info_y,
            f"Position: ({self._sel_x}, {self._sel_y})  Size: {self._sel_size}x{self._sel_size}"
        )

        # 操作提示
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 180))
        hint_y = info_y + 20 if info_y > self._sel_y else info_y + 20
        painter.drawText(
            self._sel_x, hint_y,
            "Drag to move | Scroll to resize | Enter to confirm | Esc to cancel"
        )

    # ==================== Mouse interaction ====================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # 检查是否点击在选择区域内
            sel_rect = QRect(self._sel_x, self._sel_y,
                             self._sel_size, self._sel_size)
            if sel_rect.contains(event.pos()):
                self._dragging = True
                self._drag_start = event.pos() - QPoint(self._sel_x, self._sel_y)
                self.setCursor(Qt.ClosedHandCursor)
            else:
                # 点击外部 = 移动到点击位置
                self._sel_x = event.pos().x() - self._sel_size // 2
                self._sel_y = event.pos().y() - self._sel_size // 2
                self._clamp_position()
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            new_pos = event.pos() - self._drag_start
            self._sel_x = new_pos.x()
            self._sel_y = new_pos.y()
            self._clamp_position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self._sel_size = min(self.MAX_SIZE, self._sel_size + self.SIZE_STEP)
        else:
            self._sel_size = max(self.MIN_SIZE, self._sel_size - self.SIZE_STEP)
        self._clamp_position()
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            logger.info("Minimap selection confirmed: %s", self.selection)
            self.selection_confirmed.emit(self.selection)
            self.close()
        elif event.key() == Qt.Key_Escape:
            logger.info("Minimap selection cancelled")
            self.selection_cancelled.emit()
            self.close()
        elif event.key() == Qt.Key_Up:
            self._sel_y = max(0, self._sel_y - 5)
            self.update()
        elif event.key() == Qt.Key_Down:
            self._sel_y += 5
            self._clamp_position()
            self.update()
        elif event.key() == Qt.Key_Left:
            self._sel_x = max(0, self._sel_x - 5)
            self.update()
        elif event.key() == Qt.Key_Right:
            self._sel_x += 5
            self._clamp_position()
            self.update()

    def _clamp_position(self):
        """确保选择区域在屏幕范围内"""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self._sel_x = max(0, min(geo.width() - self._sel_size, self._sel_x))
            self._sel_y = max(0, min(geo.height() - self._sel_size, self._sel_y))
