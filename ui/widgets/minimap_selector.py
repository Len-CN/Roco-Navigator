"""
小地图区域选择器

透明悬浮窗，让用户通过拖动和缩放选择游戏中小地图的位置和大小。
支持预设位置、边缘拖拽缩放、改进的提示面板。
"""

import logging
import time
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QPoint, QRect, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPainterPath,
    QMouseEvent, QWheelEvent, QKeyEvent, QFontMetrics
)

logger = logging.getLogger(__name__)

# Edge drag zone width (pixels)
EDGE_ZONE = 15
UI_FONT = "Microsoft YaHei UI"


class MinimapSelector(QWidget):
    """
    小地图区域选择器

    一个半透明的悬浮窗口，用户可以:
    - 拖动选择小地图位置
    - 滚轮 / 边缘拖拽调整大小
    - 方向键微调 (5px)
    - 1-4 数字键: 预设位置 (右上/左上/左下/右下)
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

        # 交互状态
        self._dragging = False
        self._drag_start = QPoint()
        self._edge_resizing = False  # 边缘拖拽缩放中
        self._resize_start_pos = QPoint()
        self._resize_start_size = 0

        # 大小限制反馈 (闪红)
        self._limit_flash_time: float = 0.0

        # 屏幕尺寸缓存
        self._screen_w = 1920
        self._screen_h = 1080

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
            self._screen_w = geo.width()
            self._screen_h = geo.height()

        self.setCursor(Qt.CrossCursor)

        # 闪红动画定时器
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.update)

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

    # ==================== Preset positions ====================

    def _apply_preset(self, preset: int):
        """Apply a preset position (1=right-top, 2=left-top, 3=left-bottom, 4=right-bottom)."""
        size = 180
        margin = 40
        if preset == 1:  # 右上角 (最常见)
            x = self._screen_w - size - margin
            y = margin
        elif preset == 2:  # 左上角
            x = margin
            y = margin
        elif preset == 3:  # 左下角
            x = margin
            y = self._screen_h - size - margin
        elif preset == 4:  # 右下角
            x = self._screen_w - size - margin
            y = self._screen_h - size - margin
        else:
            return

        self._sel_x = x
        self._sel_y = y
        self._sel_size = size
        self._clamp_position()
        self.update()

    # ==================== Edge detection ====================

    def _is_on_edge(self, pos: QPoint) -> bool:
        """Check if mouse position is near the circle edge."""
        cx = self._sel_x + self._sel_size // 2
        cy = self._sel_y + self._sel_size // 2
        radius = self._sel_size // 2
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = (dx * dx + dy * dy) ** 0.5
        return abs(dist - radius) < EDGE_ZONE

    # ==================== Size limit flash ====================

    def _trigger_limit_flash(self):
        """Trigger a brief red flash on the border."""
        self._limit_flash_time = time.monotonic()
        self.update()
        self._flash_timer.start(300)

    def _is_flashing(self) -> bool:
        return (time.monotonic() - self._limit_flash_time) < 0.3

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

        # 外圈 - 主边框 (闪红时变红)
        if self._is_flashing():
            border_color = QColor(245, 101, 101, 240)  # 红色闪烁
        else:
            border_color = QColor(102, 126, 234, 220)  # 蓝紫色 #667eea
        pen = QPen(border_color, 3)
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

        # ── 提示面板 (屏幕顶部居中) ──
        self._draw_hint_panel(painter)

    def _draw_hint_panel(self, painter: QPainter):
        """绘制屏幕顶部居中的半透明提示卡片"""
        lines = [
            f"小地图校准 — 将圆圈对准游戏中的小地图   "
            f"位置: ({self._sel_x}, {self._sel_y})  大小: {self._sel_size}",
            "拖拽移动 | 滚轮/边缘拖拽缩放 | 方向键微调(5px)",
            "1-4: 预设位置(右上/左上/左下/右下) | Enter: 确认 | Esc: 取消",
        ]

        font_title = QFont(UI_FONT, 13, QFont.Bold)
        font_body = QFont(UI_FONT, 11)
        fm_title = QFontMetrics(font_title)
        fm_body = QFontMetrics(font_body)

        line_heights = [fm_title.height(), fm_body.height(), fm_body.height()]
        text_widths = [
            fm_title.horizontalAdvance(lines[0]),
            fm_body.horizontalAdvance(lines[1]),
            fm_body.horizontalAdvance(lines[2]),
        ]

        pad_h = 14
        pad_v = 10
        card_w = max(text_widths) + pad_h * 2
        card_h = sum(line_heights) + pad_v * 2 + 8  # 8px line spacing total
        card_x = (self._screen_w - card_w) // 2
        card_y = 18

        # Card background
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(card_x, card_y, card_w, card_h), 12, 12)
        painter.fillPath(card_path, QColor(30, 30, 40, 200))

        # Border
        painter.setPen(QPen(QColor(102, 126, 234, 150), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(card_path)

        # Text
        tx = card_x + pad_h
        ty = card_y + pad_v + fm_title.ascent()

        painter.setPen(QColor(255, 255, 255, 240))
        painter.setFont(font_title)
        painter.drawText(tx, ty, lines[0])

        painter.setFont(font_body)
        painter.setPen(QColor(200, 210, 225, 200))
        ty += line_heights[0] + 4
        painter.drawText(tx, ty, lines[1])

        ty += line_heights[1] + 4
        painter.drawText(tx, ty, lines[2])

    # ==================== Mouse interaction ====================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Check edge first (resize)
            if self._is_on_edge(event.pos()):
                self._edge_resizing = True
                self._resize_start_pos = event.pos()
                self._resize_start_size = self._sel_size
                self.setCursor(Qt.SizeFDiagCursor)
                return

            # Check if inside selection (drag)
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
        if self._edge_resizing:
            # Calculate size change based on mouse distance from center
            cx = self._sel_x + self._sel_size // 2
            cy = self._sel_y + self._sel_size // 2
            dx = event.pos().x() - cx
            dy = event.pos().y() - cy
            new_radius = int((dx * dx + dy * dy) ** 0.5)
            new_size = new_radius * 2

            old_size = self._sel_size
            self._sel_size = max(self.MIN_SIZE, min(self.MAX_SIZE, new_size))

            # Keep center position
            self._sel_x = cx - self._sel_size // 2
            self._sel_y = cy - self._sel_size // 2

            # Flash if hit limit
            if new_size <= self.MIN_SIZE or new_size >= self.MAX_SIZE:
                if old_size != self._sel_size or not self._is_flashing():
                    self._trigger_limit_flash()

            self._clamp_position()
            self.update()
            return

        if self._dragging:
            new_pos = event.pos() - self._drag_start
            self._sel_x = new_pos.x()
            self._sel_y = new_pos.y()
            self._clamp_position()
            self.update()
            return

        # Update cursor based on hover position
        if self._is_on_edge(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            sel_rect = QRect(self._sel_x, self._sel_y,
                             self._sel_size, self._sel_size)
            if sel_rect.contains(event.pos()):
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._edge_resizing = False
            # Update cursor
            if self._is_on_edge(event.pos()):
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        old_size = self._sel_size
        if delta > 0:
            self._sel_size = min(self.MAX_SIZE, self._sel_size + self.SIZE_STEP)
        else:
            self._sel_size = max(self.MIN_SIZE, self._sel_size - self.SIZE_STEP)

        if self._sel_size == old_size:
            self._trigger_limit_flash()

        self._clamp_position()
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            logger.info("Minimap selection confirmed: %s", self.selection)
            self.selection_confirmed.emit(self.selection)
            self.close()
        elif key == Qt.Key_Escape:
            logger.info("Minimap selection cancelled")
            self.selection_cancelled.emit()
            self.close()
        elif key == Qt.Key_Up:
            self._sel_y = max(0, self._sel_y - 5)
            self.update()
        elif key == Qt.Key_Down:
            self._sel_y += 5
            self._clamp_position()
            self.update()
        elif key == Qt.Key_Left:
            self._sel_x = max(0, self._sel_x - 5)
            self.update()
        elif key == Qt.Key_Right:
            self._sel_x += 5
            self._clamp_position()
            self.update()
        # Preset positions
        elif key == Qt.Key_1:
            self._apply_preset(1)
        elif key == Qt.Key_2:
            self._apply_preset(2)
        elif key == Qt.Key_3:
            self._apply_preset(3)
        elif key == Qt.Key_4:
            self._apply_preset(4)

    def _clamp_position(self):
        """确保选择区域在屏幕范围内"""
        self._sel_x = max(0, min(self._screen_w - self._sel_size, self._sel_x))
        self._sel_y = max(0, min(self._screen_h - self._sel_size, self._sel_y))
