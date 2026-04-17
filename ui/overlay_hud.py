"""
悬浮窗 HUD - 导航地图式设计

透明置顶悬浮窗，显示:
- 地图视图 (以玩家为中心, 300x300)
- 玩家位置标记 (红色三角箭头 + 朝向)
- 路线显示 (蓝紫色路径线)
- 目标标记 (绿色旗帜)
- 指北针 (右上角)
- 导航信息 (目标名称、距离、ETA、进度条)

新拟物派 (Neumorphism) 设计风格。
"""

import logging
import math
import numpy as np
from typing import Optional, List, Tuple

from PyQt5.QtWidgets import QWidget, QApplication, QMenu, QAction
from PyQt5.QtCore import (
    Qt, QPointF, QRectF, QRect, QTimer, QPoint, pyqtSignal
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QImage, QPixmap, QRadialGradient,
    QMouseEvent, QWheelEvent, QRegion
)

from roco_navigator.ui.widgets.neumorphic import (
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT, SUCCESS, ERROR, SHADOW_DARK, SHADOW_LIGHT
)

logger = logging.getLogger(__name__)


class OverlayHUD(QWidget):
    """
    导航式悬浮窗 HUD

    包含地图视图、玩家标记、路线显示、指北针、导航信息。
    始终置顶，半透明，可拖动。
    """

    # 信号
    closed = pyqtSignal()
    lock_toggled = pyqtSignal(bool)
    crop_size_changed = pyqtSignal(int)
    size_changed = pyqtSignal(int, int)      # width, height
    shape_changed = pyqtSignal(str)          # shape name

    # 尺寸预设
    SIZES = {
        "小": (240, 310),
        "中": (320, 400),
        "大": (400, 500),
    }

    # 边缘拖拽检测区域 (px)
    RESIZE_EDGE = 8

    def __init__(self, parent=None, size: str = "中",
                 custom_w: int = 0, custom_h: int = 0,
                 shape: str = "rounded_rect"):
        super().__init__(parent)

        # 窗口设置
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # 尺寸: custom overrides preset
        if custom_w > 0 and custom_h > 0:
            w, h = custom_w, custom_h
        else:
            w, h = self.SIZES.get(size, self.SIZES["中"])

        self.setMinimumSize(180, 200)
        self.setMaximumSize(800, 800)
        self.resize(w, h)

        # 布局参数 (根据尺寸自适应)
        self._padding = 10
        self._info_height = 75
        self._map_size = 0  # computed in _update_layout
        self._map_rect = QRect()
        self._info_rect = QRect()

        # 形状: "rounded_rect", "circle"
        self._shape = shape if shape in ("rounded_rect", "circle") else "rounded_rect"

        # 数据
        self._map_crop: Optional[np.ndarray] = None
        self._player_rel_pos: Optional[Tuple[float, float]] = None  # 玩家在裁剪图中的相对坐标
        self._player_direction: float = 0.0        # 度, 0=北
        self._route_rel_points: List[Tuple[float, float]] = []  # 路线在裁剪图中的相对坐标
        self._target_rel_pos: Optional[Tuple[float, float]] = None
        self._target_name: str = ""
        self._distance: float = 0.0
        self._eta_seconds: float = 0.0
        self._progress: float = 0.0                # 0.0 - 1.0
        self._current_index: int = 0
        self._total_targets: int = 0
        self._crop_scale: float = 1.0              # 裁剪图到显示区域的缩放比
        self._direction_to_target: float = 0.0  # degrees, 0=up
        self._resource_rel_points: List[dict] = []
        self._visited_indices: set = set()
        self._current_route_index: int = 0

        # 地图缩放
        self._crop_size: int = 350

        # 交互状态
        self._dragging = False
        self._drag_start = QPoint()
        self._locked = False
        self._opacity = 0.92
        self._resizing = False        # 边缘拖拽缩放中
        self._resize_edge = ""        # "right", "bottom", "corner"
        self._resize_start = QPoint()
        self._resize_start_w = 0
        self._resize_start_h = 0

        # 缓存
        self._bg_cache: Optional[QPixmap] = None
        self._icon_cache: dict = {}  # {mark_type_id: QPixmap} 来自 MapCanvas
        self._hud_icon_size: int = 16  # HUD 上图标尺寸

        self._passthrough = False

        # Compute initial layout
        self._update_layout()

        logger.info("OverlayHUD created (%dx%d, shape=%s)", w, h, shape)

    # ==================== 数据更新 ====================

    def update_navigation(self,
                          map_crop: Optional[np.ndarray],
                          player_rel: Optional[Tuple[float, float]],
                          player_direction: float,
                          route_rel: List[Tuple[float, float]],
                          target_rel: Optional[Tuple[float, float]],
                          target_name: str,
                          distance_val: float,
                          eta: float,
                          progress: float,
                          current_idx: int,
                          total: int,
                          direction_to_target: float = 0.0,
                           resource_rel_points: Optional[List[dict]] = None,
                           visited_indices: Optional[set] = None,
                           current_route_index: int = 0):
        """
        更新所有导航数据

        坐标都是相对于 map_crop 图像的像素坐标。

        Args:
            map_crop: 地图裁剪 (BGR numpy array, 以玩家为中心)
            player_rel: 玩家在裁剪图中的位置 (x, y)
            player_direction: 玩家朝向 (0-360, 0=北)
            route_rel: 路线点在裁剪图中的相对坐标
            target_rel: 当前目标在裁剪图中的相对坐标
            target_name: 目标名称
            distance_val: 到目标的距离
            eta: 预计到达时间 (秒)
            progress: 总进度 (0-1)
            current_idx: 当前目标索引
            total: 总目标数
            resource_rel_points: 资源点在裁剪图中的相对坐标列表
        """
        self._map_crop = map_crop
        self._player_rel_pos = player_rel
        self._player_direction = player_direction
        self._route_rel_points = route_rel
        self._target_rel_pos = target_rel
        self._target_name = target_name
        self._distance = distance_val
        self._eta_seconds = eta
        self._progress = progress
        self._current_index = current_idx
        self._total_targets = total
        self._direction_to_target = direction_to_target
        self._resource_rel_points = resource_rel_points or []
        self._visited_indices = visited_indices or set()
        self._current_route_index = current_route_index

        # 计算缩放比
        if map_crop is not None:
            crop_h, crop_w = map_crop.shape[:2]
            self._crop_scale = self._map_size / max(crop_w, crop_h)

        self.update()  # 触发重绘

    def set_opacity(self, opacity: float):
        self._opacity = max(0.3, min(1.0, opacity))
        self.update()

    def set_locked(self, locked: bool):
        self._locked = locked
        self.lock_toggled.emit(locked)

    # ==================== 绘制 ====================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        painter.setOpacity(self._opacity)

        # 1. 主背景
        self._draw_background(painter)

        # 2. 地图区域
        self._draw_map_area(painter)

        # 2.5. 资源点
        self._draw_resource_points(painter)

        # 3. 信息区域 (圆形模式无信息栏)
        if self._shape != "circle":
            self._draw_info_area(painter)

    def _draw_background(self, painter: QPainter):
        """绘制新拟物派背景"""
        path = QPainterPath()
        if self._shape == "circle":
            path.addEllipse(QRectF(self.rect()))
        else:  # rounded_rect
            path.addRoundedRect(QRectF(self.rect()), 16, 16)

        # 主背景色
        painter.fillPath(path, QColor(BG_PRIMARY))

        # 微妙渐变增加立体感
        gradient = QRadialGradient(
            self.width() / 2, self.height() / 3,
            max(self.width(), self.height())
        )
        gradient.setColorAt(0, QColor(255, 255, 255, 20))
        gradient.setColorAt(1, QColor(184, 188, 194, 15))
        painter.fillPath(path, gradient)

        if self._shape == "circle":
            # 新拟物派：暗影层 + 高光层 + 主体 + 内凹边
            cx, cy = self.width() / 2, self.height() / 2
            r = min(cx, cy) - 4  # 留出阴影空间

            painter.setPen(Qt.NoPen)

            # 1) 右下暗影 (偏移 +3,+3)
            painter.setBrush(QColor(SHADOW_DARK))
            painter.drawEllipse(QPointF(cx + 3, cy + 3), r, r)

            # 2) 左上高光 (偏移 -3,-3)
            painter.setBrush(QColor(255, 255, 255, 200))
            painter.drawEllipse(QPointF(cx - 3, cy - 3), r, r)

            # 3) 主体圆 (覆盖阴影，露出边缘)
            painter.setBrush(QColor(BG_PRIMARY))
            painter.drawEllipse(QPointF(cx, cy), r, r)

            # 4) 主体上的微妙径向渐变
            body_grad = QRadialGradient(cx, cy * 0.7, r * 1.2)
            body_grad.setColorAt(0, QColor(255, 255, 255, 30))
            body_grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(body_grad)
            painter.drawEllipse(QPointF(cx, cy), r, r)

            # 5) 内凹边框 (深色内圈 + 浅色内高光弧)
            inner_r = r - self._padding
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(SHADOW_DARK), 1.5))
            painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)
            highlight_pen = QPen(QColor(255, 255, 255, 120), 1.5)
            highlight_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(highlight_pen)
            arc_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            painter.drawArc(arc_rect, 110 * 16, 160 * 16)

    def _draw_map_area(self, painter: QPainter):
        """绘制地图区域"""
        painter.save()

        # 内凹容器 (圆形模式用圆形裁剪)
        map_path = QPainterPath()
        if self._shape == "circle":
            map_path.addEllipse(QRectF(self._map_rect))
        else:
            map_path.addRoundedRect(QRectF(self._map_rect), 12, 12)
        painter.setClipPath(map_path)

        # 容器背景
        painter.fillPath(map_path, QColor("#d1d5db"))

        # 地图图像
        if self._map_crop is not None:
            self._draw_map_image(painter)

        # 路线
        if self._route_rel_points:
            self._draw_route(painter)

        # 目标标记
        if self._target_rel_pos:
            self._draw_target(painter)

        # 玩家标记
        if self._player_rel_pos:
            self._draw_player(painter)

        # 指北针
        self._draw_compass(painter)

        painter.restore()

    def _draw_map_image(self, painter: QPainter):
        """绘制地图图像"""
        crop = self._map_crop
        h, w = crop.shape[:2]
        if len(crop.shape) == 3 and crop.shape[2] == 3:
            bpl = 3 * w
            fmt = QImage.Format_RGB888
            q_img = QImage(crop.data, w, h, bpl, fmt).rgbSwapped()
        else:
            q_img = QImage(crop.data, w, h, w, QImage.Format_Grayscale8)

        scaled = q_img.scaled(
            self._map_rect.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        x = self._map_rect.x() + (self._map_rect.width() - scaled.width()) // 2
        y = self._map_rect.y() + (self._map_rect.height() - scaled.height()) // 2
        painter.drawImage(x, y, scaled)

    def _rel_to_screen(self, rx: float, ry: float) -> QPointF:
        """裁剪图相对坐标转屏幕坐标"""
        sx = self._map_rect.x() + rx * self._crop_scale
        sy = self._map_rect.y() + ry * self._crop_scale
        return QPointF(sx, sy)

    def _draw_route(self, painter: QPainter):
        """绘制路线 (visited segments in gray)"""
        if len(self._route_rel_points) < 2:
            return

        painter.save()

        # Draw segments
        for i in range(len(self._route_rel_points) - 1):
            p1 = self._rel_to_screen(*self._route_rel_points[i])
            p2 = self._rel_to_screen(*self._route_rel_points[i + 1])

            if (i + 1) in self._visited_indices or i + 1 < self._current_route_index:
                pen = QPen(QColor("#c0c4ca"), 2, Qt.SolidLine)
            else:
                pen = QPen(QColor(ACCENT), 3, Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

        # Draw waypoints
        for i, pt in enumerate(self._route_rel_points):
            if i == 0:
                continue
            sp = self._rel_to_screen(*pt)

            if i == self._current_route_index:
                painter.setBrush(QColor(SUCCESS))
                painter.setPen(QPen(QColor("#ffffff"), 2))
                r = 6
            elif i in self._visited_indices or i < self._current_route_index:
                painter.setBrush(QColor("#a0aec0"))
                painter.setPen(QPen(QColor("#d1d5db"), 1))
                r = 4
            else:
                painter.setBrush(QColor(ACCENT))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                r = 5

            painter.drawEllipse(sp, r, r)

            # Number label
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
            painter.drawText(int(sp.x()) - 3, int(sp.y()) + 3, str(i))

        painter.restore()

    def _draw_player(self, painter: QPainter):
        """绘制玩家标记 (红色三角箭头)"""
        sp = self._rel_to_screen(*self._player_rel_pos)

        painter.save()
        painter.translate(sp)
        painter.rotate(self._player_direction)

        # 方向箭头
        arrow = QPainterPath()
        arrow.moveTo(0, -14)
        arrow.lineTo(-8, 8)
        arrow.lineTo(0, 4)
        arrow.lineTo(8, 8)
        arrow.closeSubpath()

        painter.setBrush(QColor(ERROR))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawPath(arrow)

        # 中心圆点
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), 3, 3)

        painter.restore()

    def _draw_target(self, painter: QPainter):
        """绘制目标标记 (绿色旗帜)"""
        sp = self._rel_to_screen(*self._target_rel_pos)

        painter.save()

        # 旗帜杆
        painter.setPen(QPen(QColor(SUCCESS), 2))
        painter.drawLine(sp, sp + QPointF(0, -22))

        # 旗帜
        flag = QPainterPath()
        flag.moveTo(sp.x(), sp.y() - 22)
        flag.lineTo(sp.x() + 14, sp.y() - 16)
        flag.lineTo(sp.x(), sp.y() - 10)
        flag.closeSubpath()
        painter.fillPath(flag, QColor(SUCCESS))

        # 脉动圆圈
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(SUCCESS), 1.5, Qt.DashLine))
        painter.drawEllipse(sp, 12, 12)

        painter.restore()

    def _draw_compass(self, painter: QPainter):
        """绘制目标方向指示器 (右上角) — 仅在有目标时显示"""
        if not self._target_rel_pos:
            return  # 无目标时不显示

        painter.save()

        cx = self._map_rect.right() - 25
        cy = self._map_rect.top() + 25
        painter.translate(cx, cy)

        # 背景圆
        painter.setBrush(QColor(BG_PRIMARY))
        painter.setPen(QPen(QColor(TEXT_SECONDARY), 1.5))
        painter.setOpacity(0.9)
        painter.drawEllipse(QPointF(0, 0), 20, 20)
        painter.setOpacity(self._opacity)

        # 指向目标的箭头
        painter.rotate(self._direction_to_target)
        arrow = QPainterPath()
        arrow.moveTo(0, -15)
        arrow.lineTo(-5, 5)
        arrow.lineTo(0, 1)
        arrow.lineTo(5, 5)
        arrow.closeSubpath()
        painter.setBrush(QColor(SUCCESS))
        painter.setPen(Qt.NoPen)
        painter.drawPath(arrow)

        painter.restore()

    def _draw_resource_points(self, painter: QPainter):
        """绘制路线规划中的资源点 (优先用图标，回退到彩色圆点)"""
        if not self._resource_rel_points:
            return

        painter.save()
        half = self._hud_icon_size // 2
        for res in self._resource_rel_points:
            rx = res.get("rx", 0) * self._crop_scale + self._map_rect.x()
            ry = res.get("ry", 0) * self._crop_scale + self._map_rect.y()

            if not self._map_rect.contains(int(rx), int(ry)):
                continue

            # 优先用资源图标
            mt = res.get("mark_type", 0)
            icon = self._icon_cache.get(mt) if mt else None
            if icon and not icon.isNull():
                scaled = icon.scaled(
                    self._hud_icon_size, self._hud_icon_size,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                painter.drawPixmap(int(rx) - half, int(ry) - half, scaled)
            else:
                # 回退：彩色圆点
                painter.setBrush(QColor("#ed8936"))
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.drawEllipse(QPointF(rx, ry), 4, 4)

        painter.restore()

    def _draw_info_area(self, painter: QPainter):
        """绘制信息区域"""
        painter.save()

        # 信息卡片背景
        info_path = QPainterPath()
        info_path.addRoundedRect(QRectF(self._info_rect), 10, 10)
        painter.fillPath(info_path, QColor(BG_SECONDARY))

        x0 = self._info_rect.x() + 12
        y0 = self._info_rect.y()

        # 目标名称
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        name = self._target_name if self._target_name else "无目标"
        painter.drawText(x0, y0 + 22, name)

        # 距离 + ETA
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont("Microsoft YaHei", 10))

        dist_text = f"距离: {self._distance:.0f}"
        eta_text = f"预计: {self._eta_seconds:.0f}秒" if self._eta_seconds < 9999 else "预计: --"
        progress_text = f"{self._current_index}/{self._total_targets}"

        painter.drawText(x0, y0 + 42, dist_text)
        painter.drawText(x0 + 100, y0 + 42, eta_text)
        painter.drawText(self._info_rect.right() - 45, y0 + 42, progress_text)

        # 进度条
        bar_x = x0
        bar_y = y0 + 52
        bar_w = self._info_rect.width() - 24
        bar_h = 6

        # 背景
        painter.setBrush(QColor("#d1d5db"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        # 填充
        fill_w = int(bar_w * max(0, min(1, self._progress)))
        if fill_w > 0:
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)

        painter.restore()

    # ==================== 布局计算 ====================

    def _update_layout(self):
        """根据当前窗口尺寸重算内部布局"""
        w, h = self.width(), self.height()

        if self._shape == "circle":
            # 圆形模式: 强制正方形 + 纯地图
            side = min(w, h)
            if w != side or h != side:
                self.resize(side, side)
                return  # resize 会再次触发 _update_layout
            self._map_size = side - self._padding * 2
            self._map_size = max(50, self._map_size)
            offset_x = (w - self._map_size) // 2
            offset_y = (h - self._map_size) // 2
            self._map_rect = QRect(offset_x, offset_y, self._map_size, self._map_size)
            self._info_rect = QRect()
        else:
            # 圆角矩形: 完整 UI (地图 + 信息栏)
            self._map_size = min(w - self._padding * 2,
                                 h - self._info_height - self._padding * 2 - 8)
            self._map_size = max(50, self._map_size)
            self._map_rect = QRect(
                self._padding, self._padding,
                self._map_size, self._map_size
            )
            self._info_rect = QRect(
                self._padding, self._padding + self._map_size + 8,
                w - self._padding * 2, self._info_height
            )

        # 不用 setMask — 靠 QPainterPath + 透明背景实现抗锯齿边缘
        self.clearMask()

        self._bg_cache = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_layout()

    # ==================== 形状 ====================

    def set_shape(self, shape: str):
        """设置形状: rounded_rect(完整UI), circle(纯地图)"""
        if shape not in ("rounded_rect", "circle"):
            shape = "rounded_rect"
        old_shape = self._shape
        self._shape = shape

        # 切换时调整窗口尺寸
        if old_shape == "circle" and shape == "rounded_rect":
            # 从圆切方：增加高度容纳信息栏
            w = self.width()
            self.resize(w, w + self._info_height + 8)
        elif old_shape == "rounded_rect" and shape == "circle":
            # 从方切圆：取宽度做正方形
            side = self.width()
            self.resize(side, side)

        self._update_layout()
        self.shape_changed.emit(shape)

    @property
    def hud_shape(self) -> str:
        return self._shape

    # ==================== 交互 ====================

    def _detect_edge(self, pos: QPoint) -> str:
        """Detect which resize edge the mouse is on. Returns '', 'right', 'bottom', 'corner'."""
        w, h = self.width(), self.height()
        on_right = (w - self.RESIZE_EDGE) <= pos.x() <= w
        on_bottom = (h - self.RESIZE_EDGE) <= pos.y() <= h
        if on_right and on_bottom:
            return "corner"
        elif on_right:
            return "right"
        elif on_bottom:
            return "bottom"
        return ""

    def set_passthrough_locked(self, enabled: bool):
        """设置穿透锁定状态（合并 lock + passthrough）"""
        if enabled:
            self._locked = True
            self._passthrough = True
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
        else:
            self._locked = False
            self._passthrough = False
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowTransparentForInput)
        self.show()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self._locked:
            edge = self._detect_edge(event.pos())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start = event.globalPos()
                self._resize_start_w = self.width()
                self._resize_start_h = self.height()
            else:
                self._dragging = True
                self._drag_start = event.globalPos() - self.pos()
                self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._resizing:
            delta = event.globalPos() - self._resize_start
            new_w = self._resize_start_w
            new_h = self._resize_start_h
            if self._resize_edge in ("right", "corner"):
                new_w = max(180, min(800, self._resize_start_w + delta.x()))
            if self._resize_edge in ("bottom", "corner"):
                new_h = max(200, min(800, self._resize_start_h + delta.y()))
            # 圆形模式强制正方形：跟随被拖拽的边
            if self._shape == "circle":
                if self._resize_edge == "right":
                    new_h = new_w
                elif self._resize_edge == "bottom":
                    new_w = new_h
                else:  # corner
                    side = new_w if abs(delta.x()) >= abs(delta.y()) else new_h
                    new_w = new_h = side
            self.resize(new_w, new_h)
            return

        if self._dragging:
            self.move(event.globalPos() - self._drag_start)
            return

        # Update cursor based on hover edge
        if not self._locked:
            edge = self._detect_edge(event.pos())
            if edge == "corner":
                self.setCursor(Qt.SizeFDiagCursor)
            elif edge == "right":
                self.setCursor(Qt.SizeHorCursor)
            elif edge == "bottom":
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self._resizing:
                self._resizing = False
                self.size_changed.emit(self.width(), self.height())
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent):
        """Scroll wheel adjusts map crop size (zoom level)."""
        if self._locked:
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._crop_size = max(100, self._crop_size - 50)
        else:
            self._crop_size = min(1500, self._crop_size + 50)
        self.crop_size_changed.emit(self._crop_size)
        self.update()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {SHADOW_DARK};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {ACCENT};
                color: white;
            }}
        """)

        # 预设大小
        size_menu = menu.addMenu("预设大小")
        for name, (w, h) in self.SIZES.items():
            a = size_menu.addAction(f"{name} ({w}x{h})")
            a.triggered.connect(lambda checked, s=name: self._resize_to(s))

        # 当前大小
        cur_w, cur_h = self.width(), self.height()
        save_action = menu.addAction(f"当前大小: {cur_w}x{cur_h}")
        save_action.setEnabled(False)

        menu.addSeparator()

        # 形状子菜单
        shape_menu = menu.addMenu("形状")
        shapes = [
            ("圆角矩形 (完整)", "rounded_rect"),
            ("圆形 (纯地图)", "circle"),
        ]
        for label, shape_key in shapes:
            a = shape_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self._shape == shape_key)
            a.triggered.connect(
                lambda checked, s=shape_key: self.set_shape(s)
            )

        menu.addSeparator()

        # 地图缩放
        zoom_menu = menu.addMenu("地图缩放")
        for name, crop_val in [("极近 (150)", 150), ("近 (250)", 250), ("中 (350)", 350),
                                ("远 (500)", 500), ("极远 (750)", 750)]:
            a = zoom_menu.addAction(name)
            a.triggered.connect(lambda checked, v=crop_val: self._set_crop_size(v))

        custom_zoom = zoom_menu.addAction("自定义...")
        custom_zoom.triggered.connect(self._on_custom_zoom)

        menu.addSeparator()

        close_action = menu.addAction("关闭悬浮窗")
        close_action.triggered.connect(self._on_close)

        menu.exec_(pos)

    def _resize_to(self, size_name: str):
        w, h = self.SIZES.get(size_name, self.SIZES["中"])
        self.resize(w, h)
        self.size_changed.emit(w, h)

    def _on_close(self):
        self.hide()
        self.closed.emit()

    def _set_crop_size(self, size: int):
        self._crop_size = size
        self.crop_size_changed.emit(size)

    def _on_custom_zoom(self):
        from PyQt5.QtWidgets import QInputDialog
        val, ok = QInputDialog.getInt(
            self, "自定义缩放", "地图裁剪大小 (像素):",
            value=self._crop_size, min=100, max=1500, step=50
        )
        if ok:
            self._set_crop_size(val)

    def set_icon_cache(self, cache: dict):
        """接收 MapCanvas 的图标缓存 {mark_type_id: QPixmap}"""
        self._icon_cache = cache

    @property
    def crop_size(self) -> int:
        return self._crop_size

    # ==================== 属性 ====================

    @property
    def is_locked(self) -> bool:
        return self._locked
