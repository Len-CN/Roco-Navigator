"""
地图画布组件

负责显示世界地图、玩家位置、资源点和路线。
支持缩放、平移操作。
新拟物派设计风格。
"""

import logging
import numpy as np
from typing import Optional, List, Tuple

from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QImage, QPixmap, QPen, QBrush,
    QFont, QPainterPath, QWheelEvent, QMouseEvent, QTransform
)

logger = logging.getLogger(__name__)


class MapCanvas(QWidget):
    """地图画布"""

    # 信号
    position_clicked = pyqtSignal(float, float)  # 点击地图上的位置

    # 缩放限制
    MIN_ZOOM = 0.1
    MAX_ZOOM = 5.0
    ZOOM_STEP = 0.15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)

        # 样式
        self.setStyleSheet("""
            QWidget {
                background-color: #d8dce3;
                border-radius: 16px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor("#b8bcc2"))
        shadow.setOffset(6, 6)
        self.setGraphicsEffect(shadow)

        # 地图数据
        self._map_image: Optional[QPixmap] = None
        self._map_width = 0
        self._map_height = 0

        # 视口 (viewport)
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._zoom = 1.0

        # 交互状态
        self._dragging = False
        self._drag_start = QPointF()
        self._last_offset = QPointF()

        # 玩家
        self._player_pos: Optional[QPointF] = None
        self._player_direction: float = 0.0
        self._player_visible: bool = False

        # 路线
        self._route_points: List[QPointF] = []
        self._current_target_index: int = -1

        # 资源点
        self._resource_points: List[dict] = []

        # 提示文字 (地图未加载时)
        self._placeholder_text = "地图未加载\n请加载地图以开始使用"

        # 启用鼠标追踪
        self.setMouseTracking(True)

    # ==================== Public API ====================

    def load_map_image(self, image_path: str) -> bool:
        """加载地图图像"""
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                logger.error(f"Failed to load map image: {image_path}")
                return False

            self._map_image = pixmap
            self._map_width = pixmap.width()
            self._map_height = pixmap.height()

            # 初始视口: 适应窗口
            self.fit_to_view()

            logger.info(f"Map loaded: {image_path} ({self._map_width}x{self._map_height})")
            self.update()
            return True
        except Exception as e:
            logger.error(f"Error loading map: {e}")
            return False

    def load_map_from_array(self, image_array: np.ndarray) -> bool:
        """从 numpy 数组加载地图"""
        try:
            if len(image_array.shape) == 3:
                h, w, ch = image_array.shape
                if ch == 3:
                    fmt = QImage.Format_RGB888
                    bytes_per_line = 3 * w
                elif ch == 4:
                    fmt = QImage.Format_RGBA8888
                    bytes_per_line = 4 * w
                else:
                    return False
            else:
                h, w = image_array.shape
                fmt = QImage.Format_Grayscale8
                bytes_per_line = w

            q_image = QImage(image_array.data, w, h, bytes_per_line, fmt)
            if ch == 3:
                q_image = q_image.rgbSwapped()

            self._map_image = QPixmap.fromImage(q_image)
            self._map_width = w
            self._map_height = h
            self.fit_to_view()
            self.update()
            return True
        except Exception as e:
            logger.error(f"Error loading map from array: {e}")
            return False

    def set_player_position(self, x: float, y: float, direction: float = 0.0):
        """设置玩家位置 (世界坐标)"""
        self._player_pos = QPointF(x, y)
        self._player_direction = direction
        self._player_visible = True
        self.update()

    def clear_player(self):
        self._player_visible = False
        self.update()

    def set_route(self, points: List[Tuple[float, float]], current_index: int = 0):
        """设置路线"""
        self._route_points = [QPointF(x, y) for x, y in points]
        self._current_target_index = current_index
        self.update()

    def clear_route(self):
        self._route_points = []
        self._current_target_index = -1
        self.update()

    def set_resources(self, resources: List[dict]):
        """设置资源点列表, each dict has 'x', 'y', 'name', 'type'"""
        self._resource_points = resources
        self.update()

    def fit_to_view(self):
        """适应视图"""
        if self._map_image is None:
            return
        w_ratio = self.width() / self._map_width
        h_ratio = self.height() / self._map_height
        self._zoom = min(w_ratio, h_ratio) * 0.9
        self._offset_x = (self.width() - self._map_width * self._zoom) / 2
        self._offset_y = (self.height() - self._map_height * self._zoom) / 2
        self.update()

    def center_on(self, world_x: float, world_y: float):
        """将视图中心移动到指定世界坐标"""
        self._offset_x = self.width() / 2 - world_x * self._zoom
        self._offset_y = self.height() / 2 - world_y * self._zoom
        self.update()

    def get_map_crop(self, center_x: float, center_y: float, crop_size: int = 600) -> Optional[np.ndarray]:
        """获取以指定点为中心的地图裁剪 (用于 HUD)"""
        if self._map_image is None:
            return None

        img = self._map_image.toImage()
        half = crop_size // 2
        x1 = max(0, int(center_x - half))
        y1 = max(0, int(center_y - half))
        x2 = min(self._map_width, int(center_x + half))
        y2 = min(self._map_height, int(center_y + half))

        cropped = img.copy(x1, y1, x2 - x1, y2 - y1)
        cropped = cropped.convertToFormat(QImage.Format_RGB888)

        width = cropped.width()
        height = cropped.height()
        ptr = cropped.bits()
        ptr.setsize(height * width * 3)
        arr = np.array(ptr).reshape(height, width, 3)
        return arr.copy()

    # ==================== Coordinate conversion ====================

    def world_to_screen(self, wx: float, wy: float) -> QPointF:
        sx = wx * self._zoom + self._offset_x
        sy = wy * self._zoom + self._offset_y
        return QPointF(sx, sy)

    def screen_to_world(self, sx: float, sy: float) -> QPointF:
        wx = (sx - self._offset_x) / self._zoom
        wy = (sy - self._offset_y) / self._zoom
        return QPointF(wx, wy)

    # ==================== Painting ====================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 背景
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(self.rect()), 16, 16)
        painter.setClipPath(bg_path)
        painter.fillPath(bg_path, QColor("#d8dce3"))

        if self._map_image is None:
            self._draw_placeholder(painter)
            return

        # 绘制地图
        self._draw_map(painter)

        # 绘制资源点
        self._draw_resources(painter)

        # 绘制路线
        self._draw_route(painter)

        # 绘制玩家
        if self._player_visible:
            self._draw_player(painter)

    def _draw_placeholder(self, painter: QPainter):
        painter.setPen(QColor("#a0aec0"))
        painter.setFont(QFont("Arial", 16))
        painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)

    def _draw_map(self, painter: QPainter):
        painter.save()
        painter.translate(self._offset_x, self._offset_y)
        painter.scale(self._zoom, self._zoom)
        painter.drawPixmap(0, 0, self._map_image)
        painter.restore()

    def _draw_player(self, painter: QPainter):
        if self._player_pos is None:
            return

        screen_pos = self.world_to_screen(self._player_pos.x(), self._player_pos.y())
        painter.save()
        painter.translate(screen_pos)
        painter.rotate(self._player_direction)

        # 朝向箭头
        arrow = QPainterPath()
        arrow.moveTo(0, -12)
        arrow.lineTo(-7, 7)
        arrow.lineTo(7, 7)
        arrow.closeSubpath()

        painter.setBrush(QColor("#f56565"))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawPath(arrow)

        # 中心圆点
        painter.drawEllipse(QPointF(0, 0), 4, 4)
        painter.restore()

    def _draw_route(self, painter: QPainter):
        if len(self._route_points) < 2:
            return

        painter.save()

        # 路线线条
        pen = QPen(QColor("#667eea"), max(2, int(2 / self._zoom)), Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        path = QPainterPath()
        sp = self.world_to_screen(self._route_points[0].x(), self._route_points[0].y())
        path.moveTo(sp)
        for pt in self._route_points[1:]:
            sp = self.world_to_screen(pt.x(), pt.y())
            path.lineTo(sp)
        painter.drawPath(path)

        # 路径点
        for i, pt in enumerate(self._route_points):
            sp = self.world_to_screen(pt.x(), pt.y())
            r = 5

            if i == self._current_target_index:
                # 当前目标 - 绿色
                painter.setBrush(QColor("#48bb78"))
                painter.setPen(QPen(QColor("#ffffff"), 2))
                r = 7
            else:
                painter.setBrush(QColor("#667eea"))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))

            painter.drawEllipse(sp, r, r)

        painter.restore()

    def _draw_resources(self, painter: QPainter):
        if not self._resource_points:
            return

        painter.save()
        for res in self._resource_points:
            x, y = res.get("x", 0), res.get("y", 0)
            sp = self.world_to_screen(x, y)

            # 只绘制可见区域内的资源点
            if not self.rect().contains(sp.toPoint()):
                continue

            painter.setBrush(QColor("#ed8936"))
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawEllipse(sp, 4, 4)
        painter.restore()

    # ==================== Interaction ====================

    def wheelEvent(self, event: QWheelEvent):
        """滚轮缩放"""
        old_zoom = self._zoom

        if event.angleDelta().y() > 0:
            self._zoom = min(self.MAX_ZOOM, self._zoom * (1 + self.ZOOM_STEP))
        else:
            self._zoom = max(self.MIN_ZOOM, self._zoom * (1 - self.ZOOM_STEP))

        # 以鼠标位置为缩放中心
        mouse_pos = event.position() if hasattr(event, 'position') else QPointF(event.pos())
        factor = self._zoom / old_zoom
        self._offset_x = mouse_pos.x() - (mouse_pos.x() - self._offset_x) * factor
        self._offset_y = mouse_pos.y() - (mouse_pos.y() - self._offset_y) * factor

        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = QPointF(event.pos())
            self._last_offset = QPointF(self._offset_x, self._offset_y)
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.RightButton:
            # 右键点击获取世界坐标
            world = self.screen_to_world(event.pos().x(), event.pos().y())
            self.position_clicked.emit(world.x(), world.y())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = QPointF(event.pos()) - self._drag_start
            self._offset_x = self._last_offset.x() + delta.x()
            self._offset_y = self._last_offset.y() + delta.y()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._map_image and self._zoom < self.MIN_ZOOM:
            self.fit_to_view()
