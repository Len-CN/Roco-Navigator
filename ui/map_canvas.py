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
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QLineF
from PyQt5.QtGui import (
    QPainter, QColor, QImage, QPixmap, QPen, QBrush,
    QFont, QPainterPath, QWheelEvent, QMouseEvent, QTransform
)

logger = logging.getLogger(__name__)


# 传送点 mark_type ID（来自 wiki_cache.json，"传送点"）
HUB_MARK_TYPE = 202


class MapCanvas(QWidget):
    """地图画布"""

    # 信号
    position_clicked = pyqtSignal(float, float)  # 点击地图上的位置
    region_selected = pyqtSignal(float, float, float, float)  # x1, y1, x2, y2 in world coords
    waypoint_skip_requested = pyqtSignal(int)     # 双击路线点请求跳转
    route_points_changed = pyqtSignal(object)     # emits [(x, y), ...] during manual editing

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
        self._visited_indices: set = set()
        self._teleport_segments: set = set()  # 段索引集合，i 表示 points[i]->points[i+1] 是瞬移段
        self._hub_indices: set = set()  # 路径中实际用到的传送点节点索引
        self._route_edit_mode: Optional[str] = None  # None / "draw" / "edit"
        self._selected_route_index: int = -1
        self._dragging_route_point: bool = False

        # 资源点
        self._resource_points: List[dict] = []

        # 提示文字 (地图未加载时)
        self._placeholder_text = "地图未加载\n请加载地图以开始使用"

        # 图标缓存
        self._icon_cache: dict = {}  # mark_type -> QPixmap
        self._icon_size = 24  # 显示大小

        # 显示选项
        self._show_route_line = True

        # 启用鼠标追踪
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Region selection mode (for route planning)
        self._selecting_region = False
        self._sel_start: Optional[QPointF] = None
        self._sel_current: Optional[QPointF] = None
        self._selected_region: Optional[QRectF] = None  # world coords

    # ==================== Public API ====================

    def start_region_selection(self):
        """Enter rectangle region selection mode."""
        if self.is_route_editing:
            return
        self._selecting_region = True
        self._sel_start = None
        self._sel_current = None
        self._selected_region = None
        self.setCursor(Qt.CrossCursor)
        self.update()

    def cancel_region_selection(self):
        """Cancel region selection mode."""
        self._selecting_region = False
        self._sel_start = None
        self._sel_current = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def clear_selected_region(self):
        """Clear the highlighted selected region."""
        self._selected_region = None
        self.update()

    @property
    def is_route_editing(self) -> bool:
        return self._route_edit_mode is not None

    def start_route_drawing(self, clear: bool = True):
        """进入手工路线绘制模式。"""
        self.cancel_region_selection()
        if clear:
            self.clear_route()
        self._route_edit_mode = "draw"
        self._selected_route_index = -1
        self._dragging_route_point = False
        self.setFocus(Qt.MouseFocusReason)
        self.setCursor(Qt.CrossCursor)
        self.update()

    def start_route_editing(self):
        """进入路线编辑模式。"""
        self.cancel_region_selection()
        self._route_edit_mode = "edit"
        self._selected_route_index = -1
        self._dragging_route_point = False
        self.setFocus(Qt.MouseFocusReason)
        self.setCursor(Qt.PointingHandCursor)
        self.update()

    def finish_route_editing(self):
        """退出路线绘制/编辑模式。"""
        self._route_edit_mode = None
        self._selected_route_index = -1
        self._dragging_route_point = False
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def get_route_points(self) -> List[Tuple[float, float]]:
        return [(p.x(), p.y()) for p in self._route_points]

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
            if len(image_array.shape) == 3 and image_array.shape[2] == 3:
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

    def set_route(self, points: List[Tuple[float, float]], current_index: int = 0,
                  visited: set = None, teleport_segments: Optional[set] = None,
                  hub_indices: Optional[set] = None):
        """设置路线

        Args:
            points: [(x, y), ...] 路线点列表
            current_index: 当前目标索引
            visited: 已访问的索引集合
            teleport_segments: 瞬移段索引集合，i ∈ set 表示 points[i]->points[i+1]
                               是瞬移段，绘制为虚线
            hub_indices: 路径中传送点节点的索引集合，绘制为传送点图标
        """
        self._route_points = [QPointF(x, y) for x, y in points]
        self._current_target_index = current_index
        self._visited_indices = visited or set()
        self._teleport_segments = teleport_segments or set()
        self._hub_indices = hub_indices or set()
        self.update()

    def clear_route(self):
        self._route_points = []
        self._current_target_index = -1
        self._visited_indices = set()
        self._teleport_segments = set()
        self._hub_indices = set()
        self._selected_route_index = -1
        self.update()

    def set_show_route_line(self, enabled: bool):
        self._show_route_line = enabled
        self.update()

    def update_route_progress(self, current_index: int, visited: set = None):
        """仅更新导航进度字段，保留路线/瞬移段/hub 图标。

        用于导航过程中目标递进或跳转，不重新设置整条路线。
        """
        self._current_target_index = current_index
        self._visited_indices = visited or set()
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
        if self._show_route_line:
            self._draw_route(painter)
            self._draw_route_edit_overlay(painter)

        # Draw region selection overlay
        self._draw_selection_rect(painter)

        # 绘制玩家
        if self._player_visible:
            self._draw_player(painter)

        # 起点/终点圆环置顶 — 不被玩家箭头盖住
        if self._show_route_line:
            self._draw_route_endpoints(painter)

    def _draw_placeholder(self, painter: QPainter):
        painter.setPen(QColor("#a0aec0"))
        painter.setFont(QFont("Microsoft YaHei", 16))
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

    def _draw_route_endpoints(self, painter: QPainter):
        """起点/终点圆环 — 在玩家箭头之上层绘制，确保可见。"""
        n = len(self._route_points)
        if n < 1:
            return
        is_loop = (n >= 2 and self._route_points[0] == self._route_points[-1])

        painter.save()
        # 起点 — 绿色光环（中空），玩家箭头从中露出
        sp = self.world_to_screen(self._route_points[0].x(),
                                  self._route_points[0].y())
        painter.setPen(QPen(QColor("#48bb78"), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(sp, 11, 11)
        if is_loop:
            # 环形：内嵌红心提示此处亦为终点
            painter.setBrush(QColor("#e53e3e"))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.drawEllipse(sp, 4, 4)

        # 终点 — 红实心（仅开放/指定终点；环形已在起点合并显示）
        if not is_loop and n >= 2:
            ep = self.world_to_screen(self._route_points[-1].x(),
                                      self._route_points[-1].y())
            painter.setBrush(QColor("#e53e3e"))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(ep, 7, 7)
        painter.restore()

    def _draw_route(self, painter: QPainter):
        if len(self._route_points) < 2:
            return

        painter.save()

        # Draw route segments
        for i in range(len(self._route_points) - 1):
            p1 = self.world_to_screen(self._route_points[i].x(), self._route_points[i].y())
            p2 = self.world_to_screen(self._route_points[i + 1].x(), self._route_points[i + 1].y())

            visited = (i + 1 <= self._current_target_index or
                       (i + 1) in self._visited_indices)
            is_teleport = i in self._teleport_segments
            width = max(2, int(2 / self._zoom))

            if visited:
                # Visited segment — gray (无论是否瞬移)
                pen = QPen(QColor("#c0c4ca"), width, Qt.SolidLine)
            elif is_teleport:
                # Upcoming teleport — purple dashed
                pen = QPen(QColor("#9b8cff"), width, Qt.DashLine)
            else:
                # Upcoming walk — accent blue solid
                pen = QPen(QColor("#667eea"), width, Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

        # Draw waypoints (起点/终点由 _draw_route_endpoints 在玩家箭头之上绘制，此处跳过)
        n = len(self._route_points)
        is_loop = (n >= 2 and self._route_points[0] == self._route_points[-1])

        for i, pt in enumerate(self._route_points):
            sp = self.world_to_screen(pt.x(), pt.y())

            is_start = (i == 0)
            is_end = (i == n - 1) and n >= 2

            # 起点和终点都延后到 _draw_route_endpoints
            if is_start or is_end:
                continue

            if i in self._hub_indices:
                # 路径用到的传送点 — 直接画图标
                icon = self._icon_cache.get(HUB_MARK_TYPE)
                if icon is not None:
                    half = self._icon_size // 2
                    painter.drawPixmap(int(sp.x() - half), int(sp.y() - half), icon)
                else:
                    # 图标缺失 → 紫色圆点（与瞬移段同色）
                    painter.setBrush(QColor("#9b8cff"))
                    painter.setPen(QPen(QColor("#ffffff"), 1.5))
                    painter.drawEllipse(sp, 6, 6)
                continue

            r = 5
            if i == self._current_target_index:
                painter.setBrush(QColor("#48bb78"))
                painter.setPen(QPen(QColor("#ffffff"), 2))
                r = 7
            elif i in self._visited_indices or i < self._current_target_index:
                painter.setBrush(QColor("#a0aec0"))
                painter.setPen(QPen(QColor("#d1d5db"), 1))
            else:
                painter.setBrush(QColor("#667eea"))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))

            painter.drawEllipse(sp, r, r)

        painter.restore()

    def _draw_route_edit_overlay(self, painter: QPainter):
        if not self.is_route_editing:
            return

        painter.save()
        for i, pt in enumerate(self._route_points):
            sp = self.world_to_screen(pt.x(), pt.y())
            if i == self._selected_route_index:
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(QColor("#f56565"), 3))
                painter.drawEllipse(sp, 9, 9)
            else:
                painter.setBrush(QColor("#ffffff"))
                painter.setPen(QPen(QColor("#667eea"), 2))
                painter.drawEllipse(sp, 6, 6)

            painter.setPen(QColor("#4a5568"))
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(sp + QPointF(8, -8), str(i + 1))
        painter.restore()

    def load_resource_icons(self, icons_dir: str, mark_types: list):
        """加载资源图标"""
        import os
        self._icon_cache.clear()
        if not os.path.exists(icons_dir):
            return

        for filename in os.listdir(icons_dir):
            if not filename.endswith('.png'):
                continue
            try:
                # filename format: "201_庇护所.png"
                mt_id = int(filename.split('_')[0])
                filepath = os.path.join(icons_dir, filename)

                # Use PIL to load and strip ICC profile to avoid libpng warnings
                try:
                    from PIL import Image
                    from io import BytesIO
                    pil_img = Image.open(filepath)
                    if 'icc_profile' in pil_img.info:
                        pil_img.info.pop('icc_profile')
                    buf = BytesIO()
                    pil_img.save(buf, format='PNG')
                    buf.seek(0)
                    pixmap = QPixmap()
                    pixmap.loadFromData(buf.read())
                except ImportError:
                    pixmap = QPixmap(filepath)

                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        self._icon_size, self._icon_size,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    self._icon_cache[mt_id] = scaled
            except (ValueError, Exception):
                continue

        logger.info("Loaded %d resource icons", len(self._icon_cache))

    def _draw_resources(self, painter: QPainter):
        if not self._resource_points:
            return

        painter.save()
        half = self._icon_size // 2
        
        for res in self._resource_points:
            x, y = res.get("x", 0), res.get("y", 0)
            sp = self.world_to_screen(x, y)

            if not self.rect().contains(sp.toPoint()):
                continue

            mt = res.get("mark_type", 0)
            icon = self._icon_cache.get(mt)
            
            if icon and not icon.isNull():
                painter.drawPixmap(
                    int(sp.x()) - half, int(sp.y()) - half, icon
                )
            else:
                # Fallback: colored dot
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
        if self.is_route_editing:
            self._handle_route_edit_press(event)
            return

        if self._selecting_region and event.button() == Qt.LeftButton:
            world = self.screen_to_world(event.pos().x(), event.pos().y())
            self._sel_start = world
            self._sel_current = world
            self.update()
            return
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
        if self.is_route_editing:
            self._handle_route_edit_move(event)
            return

        if self._selecting_region and self._sel_start is not None:
            world = self.screen_to_world(event.pos().x(), event.pos().y())
            self._sel_current = world
            self.update()
            return
        if self._dragging:
            delta = QPointF(event.pos()) - self._drag_start
            self._offset_x = self._last_offset.x() + delta.x()
            self._offset_y = self._last_offset.y() + delta.y()
            self.update()
            return
        # 区域选择模式下保持 CrossCursor，不做悬停判断
        if self._selecting_region:
            return
        # 悬停路线点时显示指针光标
        if self._route_points:
            if self._is_near_waypoint(event.pos().x(), event.pos().y()):
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_route_editing:
            if event.button() == Qt.LeftButton:
                self._dragging_route_point = False
            elif event.button() in (Qt.RightButton, Qt.MiddleButton):
                self._dragging = False
                self.setCursor(Qt.CrossCursor if self._route_edit_mode == "draw" else Qt.ArrowCursor)
            return

        if self._selecting_region and event.button() == Qt.LeftButton and self._sel_start is not None:
            world = self.screen_to_world(event.pos().x(), event.pos().y())
            x1 = min(self._sel_start.x(), world.x())
            y1 = min(self._sel_start.y(), world.y())
            x2 = max(self._sel_start.x(), world.x())
            y2 = max(self._sel_start.y(), world.y())
            # Only emit if the region is meaningful (> 20px in both dimensions)
            if (x2 - x1) > 20 and (y2 - y1) > 20:
                self._selected_region = QRectF(x1, y1, x2 - x1, y2 - y1)
                self.region_selected.emit(x1, y1, x2, y2)
            self._selecting_region = False
            self._sel_start = None
            self._sel_current = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
            return
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._map_image and self._zoom < self.MIN_ZOOM:
            self.fit_to_view()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.is_route_editing:
            return
        if event.button() == Qt.LeftButton:
            self._check_waypoint_click(event.pos().x(), event.pos().y())
        else:
            super().mouseDoubleClickEvent(event)

    def _is_near_waypoint(self, sx: float, sy: float, radius: int = 12) -> bool:
        """判断屏幕坐标是否在某个路线点范围内"""
        r2 = radius * radius
        for pt in self._route_points:
            sp = self.world_to_screen(pt.x(), pt.y())
            dx, dy = sx - sp.x(), sy - sp.y()
            if dx * dx + dy * dy <= r2:
                return True
        return False

    def _check_waypoint_click(self, sx: float, sy: float):
        """找最近的路线点，若在 12px 内则发射跳转信号"""
        RADIUS_SQ = 12 * 12
        best_i, best_d = -1, RADIUS_SQ
        for i, pt in enumerate(self._route_points):
            sp = self.world_to_screen(pt.x(), pt.y())
            dx, dy = sx - sp.x(), sy - sp.y()
            d = dx * dx + dy * dy
            if d <= best_d:
                best_d, best_i = d, i
        if best_i >= 0:
            self.waypoint_skip_requested.emit(best_i)

    def keyPressEvent(self, event):
        if self.is_route_editing and event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_route_point()
        elif self._selecting_region and event.key() == Qt.Key_Escape:
            self.cancel_region_selection()
        else:
            super().keyPressEvent(event)

    def _emit_route_points_changed(self):
        self.route_points_changed.emit(self.get_route_points())

    def _handle_route_edit_press(self, event: QMouseEvent):
        if event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._dragging = True
            self._drag_start = QPointF(event.pos())
            self._last_offset = QPointF(self._offset_x, self._offset_y)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() != Qt.LeftButton:
            return

        sx, sy = event.pos().x(), event.pos().y()
        world = self.screen_to_world(sx, sy)
        near_idx = self._nearest_waypoint_index(sx, sy)

        if near_idx >= 0:
            self._selected_route_index = near_idx
            self._dragging_route_point = True
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            return

        if self._route_edit_mode == "edit":
            seg_idx = self._nearest_segment_index(sx, sy)
            if seg_idx >= 0:
                self._route_points.insert(seg_idx + 1, world)
                self._selected_route_index = seg_idx + 1
                self._dragging_route_point = True
                self._clear_route_plan_metadata()
                self._emit_route_points_changed()
                self.update()
                return

        self._route_points.append(world)
        self._selected_route_index = len(self._route_points) - 1
        self._clear_route_plan_metadata()
        self._emit_route_points_changed()
        self.update()

    def _handle_route_edit_move(self, event: QMouseEvent):
        sx, sy = event.pos().x(), event.pos().y()
        if self._dragging:
            delta = QPointF(event.pos()) - self._drag_start
            self._offset_x = self._last_offset.x() + delta.x()
            self._offset_y = self._last_offset.y() + delta.y()
            self.update()
            return

        if self._dragging_route_point and 0 <= self._selected_route_index < len(self._route_points):
            self._route_points[self._selected_route_index] = self.screen_to_world(sx, sy)
            self._clear_route_plan_metadata()
            self._emit_route_points_changed()
            self.update()
            return

        if self._nearest_waypoint_index(sx, sy) >= 0:
            self.setCursor(Qt.PointingHandCursor)
        elif self._route_edit_mode == "edit" and self._nearest_segment_index(sx, sy) >= 0:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.CrossCursor if self._route_edit_mode == "draw" else Qt.ArrowCursor)

    def _delete_selected_route_point(self):
        if not (0 <= self._selected_route_index < len(self._route_points)):
            return
        self._route_points.pop(self._selected_route_index)
        if self._selected_route_index >= len(self._route_points):
            self._selected_route_index = len(self._route_points) - 1
        self._clear_route_plan_metadata()
        self._emit_route_points_changed()
        self.update()

    def _clear_route_plan_metadata(self):
        self._current_target_index = -1
        self._visited_indices = set()
        self._teleport_segments = set()
        self._hub_indices = set()

    def _nearest_waypoint_index(self, sx: float, sy: float, radius: int = 12) -> int:
        r2 = radius * radius
        best_i, best_d = -1, r2
        for i, pt in enumerate(self._route_points):
            sp = self.world_to_screen(pt.x(), pt.y())
            dx, dy = sx - sp.x(), sy - sp.y()
            d = dx * dx + dy * dy
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    def _nearest_segment_index(self, sx: float, sy: float, radius: int = 10) -> int:
        if len(self._route_points) < 2:
            return -1
        click = QPointF(sx, sy)
        best_i, best_d = -1, float(radius)
        for i in range(len(self._route_points) - 1):
            p1 = self.world_to_screen(self._route_points[i].x(), self._route_points[i].y())
            p2 = self.world_to_screen(self._route_points[i + 1].x(), self._route_points[i + 1].y())
            d = self._distance_to_segment(click, p1, p2)
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    @staticmethod
    def _distance_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
        line = QLineF(a, b)
        length = line.length()
        if length <= 0:
            dx, dy = p.x() - a.x(), p.y() - a.y()
            return (dx * dx + dy * dy) ** 0.5

        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        t = ((p.x() - ax) * (bx - ax) + (p.y() - ay) * (by - ay)) / (length * length)
        t = max(0.0, min(1.0, t))
        px = ax + t * (bx - ax)
        py = ay + t * (by - ay)
        dx, dy = p.x() - px, p.y() - py
        return (dx * dx + dy * dy) ** 0.5

    def _draw_selection_rect(self, painter: QPainter):
        """Draw the region selection rectangle (rubber band or confirmed)."""
        # Active drag
        if self._selecting_region and self._sel_start is not None and self._sel_current is not None:
            p1 = self.world_to_screen(self._sel_start.x(), self._sel_start.y())
            p2 = self.world_to_screen(self._sel_current.x(), self._sel_current.y())
            rect = QRectF(p1, p2).normalized()
            painter.save()
            painter.setBrush(QColor(102, 126, 234, 30))  # semi-transparent blue
            painter.setPen(QPen(QColor("#667eea"), 2, Qt.DashLine))
            painter.drawRect(rect)
            painter.restore()

        # Confirmed region
        if self._selected_region is not None:
            p1 = self.world_to_screen(self._selected_region.x(), self._selected_region.y())
            p2 = self.world_to_screen(
                self._selected_region.x() + self._selected_region.width(),
                self._selected_region.y() + self._selected_region.height()
            )
            rect = QRectF(p1, p2).normalized()
            painter.save()
            painter.setBrush(QColor(102, 126, 234, 20))
            painter.setPen(QPen(QColor("#667eea"), 1.5, Qt.DashLine))
            painter.drawRect(rect)
            # Label
            painter.setPen(QColor("#667eea"))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(rect.adjusted(4, 2, 0, 0), Qt.AlignLeft | Qt.AlignTop, "规划区域")
            painter.restore()
