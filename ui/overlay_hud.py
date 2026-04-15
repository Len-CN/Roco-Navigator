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
    QImage, QPixmap, QRadialGradient, QLinearGradient,
    QMouseEvent, QWheelEvent
)

logger = logging.getLogger(__name__)

# ==================== 设计常量 ====================
BG_PRIMARY = "#e0e5ec"
BG_SECONDARY = "#f0f0f3"
TEXT_PRIMARY = "#4a5568"
TEXT_SECONDARY = "#718096"
ACCENT = "#667eea"
SUCCESS = "#48bb78"
ERROR = "#f56565"
SHADOW_DARK = "#b8bcc2"


class OverlayHUD(QWidget):
    """
    导航式悬浮窗 HUD

    包含地图视图、玩家标记、路线显示、指北针、导航信息。
    始终置顶，半透明，可拖动。
    """

    # 信号
    closed = pyqtSignal()
    lock_toggled = pyqtSignal(bool)

    # 尺寸预设
    SIZES = {
        "small": (240, 310),
        "medium": (320, 400),
        "large": (400, 500),
    }

    def __init__(self, parent=None, size: str = "medium"):
        super().__init__(parent)

        # 窗口设置
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 尺寸
        w, h = self.SIZES.get(size, self.SIZES["medium"])
        self.setFixedSize(w, h)

        # 布局参数 (根据尺寸自适应)
        self._padding = 10
        self._map_size = w - self._padding * 2
        self._info_height = 75
        self._map_rect = QRect(
            self._padding, self._padding,
            self._map_size, self._map_size
        )
        self._info_rect = QRect(
            self._padding, self._padding + self._map_size + 8,
            self._map_size, self._info_height
        )

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

        # 交互状态
        self._dragging = False
        self._drag_start = QPoint()
        self._locked = False
        self._opacity = 0.92

        # 缓存
        self._bg_cache: Optional[QPixmap] = None

        logger.info("OverlayHUD created (size=%s, %dx%d)", size, w, h)

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
                          total: int):
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

        # 3. 信息区域
        self._draw_info_area(painter)

    def _draw_background(self, painter: QPainter):
        """绘制新拟物派背景"""
        path = QPainterPath()
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

    def _draw_map_area(self, painter: QPainter):
        """绘制地图区域"""
        painter.save()

        # 内凹容器
        map_path = QPainterPath()
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
        """绘制路线"""
        if len(self._route_rel_points) < 2:
            return

        painter.save()

        # 路线线条
        pen = QPen(QColor(ACCENT), 3, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        path = QPainterPath()
        p0 = self._rel_to_screen(*self._route_rel_points[0])
        path.moveTo(p0)
        for pt in self._route_rel_points[1:]:
            path.lineTo(self._rel_to_screen(*pt))
        painter.drawPath(path)

        # 路径点
        for i, pt in enumerate(self._route_rel_points):
            if i == 0:
                continue
            sp = self._rel_to_screen(*pt)
            painter.setBrush(QColor(ACCENT))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.drawEllipse(sp, 5, 5)

            # 编号
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Arial", 7, QFont.Bold))
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
        """绘制指北针 (右上角)"""
        painter.save()

        cx = self._map_rect.right() - 25
        cy = self._map_rect.top() + 25
        painter.translate(cx, cy)

        # 背景圆
        painter.setBrush(QColor(BG_PRIMARY))
        painter.setPen(QPen(QColor(TEXT_SECONDARY), 1.5))
        painter.setOpacity(0.85)
        painter.drawEllipse(QPointF(0, 0), 18, 18)
        painter.setOpacity(self._opacity)

        # 旋转指针 (反向, 保持北向上)
        painter.rotate(-self._player_direction)

        # 北向指针 (红色)
        north = QPainterPath()
        north.moveTo(0, -13)
        north.lineTo(-4, 0)
        north.lineTo(4, 0)
        north.closeSubpath()
        painter.setBrush(QColor(ERROR))
        painter.setPen(Qt.NoPen)
        painter.drawPath(north)

        # 南向指针 (灰色)
        south = QPainterPath()
        south.moveTo(0, 13)
        south.lineTo(-4, 0)
        south.lineTo(4, 0)
        south.closeSubpath()
        painter.setBrush(QColor("#a0aec0"))
        painter.drawPath(south)

        # "N" 标记
        painter.setPen(QColor(ERROR))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(-4, -15, "N")

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
        name = self._target_name if self._target_name else "No target"
        painter.drawText(x0, y0 + 22, name)

        # 距离 + ETA
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont("Arial", 10))

        dist_text = f"Dist: {self._distance:.0f}"
        eta_text = f"ETA: {self._eta_seconds:.0f}s" if self._eta_seconds < 9999 else "ETA: --"
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

    # ==================== 交互 ====================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self._locked:
            self._dragging = True
            self._drag_start = event.globalPos() - self.pos()
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self.move(event.globalPos() - self._drag_start)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

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

        lock_text = "Unlock" if self._locked else "Lock Position"
        lock_action = menu.addAction(lock_text)
        lock_action.triggered.connect(lambda: self.set_locked(not self._locked))

        menu.addSeparator()

        for name, (w, h) in self.SIZES.items():
            a = menu.addAction(f"Size: {name} ({w}x{h})")
            a.triggered.connect(lambda checked, s=name: self._resize_to(s))

        menu.addSeparator()

        close_action = menu.addAction("Close HUD")
        close_action.triggered.connect(self._on_close)

        menu.exec_(pos)

    def _resize_to(self, size_name: str):
        w, h = self.SIZES.get(size_name, self.SIZES["medium"])
        self.setFixedSize(w, h)

        self._map_size = w - self._padding * 2
        self._map_rect = QRect(
            self._padding, self._padding,
            self._map_size, self._map_size
        )
        self._info_rect = QRect(
            self._padding, self._padding + self._map_size + 8,
            self._map_size, self._info_height
        )
        self._bg_cache = None
        self.update()

    def _on_close(self):
        self.hide()
        self.closed.emit()

    # ==================== 属性 ====================

    @property
    def is_locked(self) -> bool:
        return self._locked
