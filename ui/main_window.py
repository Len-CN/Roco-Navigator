"""
主窗口

组装标题栏、侧边栏、地图画布等组件。
无边框窗口 + 新拟物派设计风格。
"""

import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QMessageBox, QGraphicsDropShadowEffect,
    QApplication, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QColor, QFont, QIcon, QResizeEvent

from roco_navigator.config.settings import Settings
from roco_navigator.ui.widgets.title_bar import TitleBar
from roco_navigator.ui.widgets.sidebar import Sidebar
from roco_navigator.ui.map_canvas import MapCanvas
from roco_navigator.ui.widgets.neumorphic import (
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT, NeumorphicLabel, StatusIndicator
)
from roco_navigator.utils.gpu_utils import GPUManager

logger = logging.getLogger(__name__)


class StatusBarWidget(QWidget):
    """自定义状态栏"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SECONDARY};
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # GPU 状态
        self._gpu_label = QLabel("CPU Mode")
        self._gpu_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._gpu_label)

        layout.addStretch()

        # FPS 显示
        self._fps_label = QLabel("-- FPS")
        self._fps_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._fps_label)

        # 位置显示
        self._pos_label = QLabel("Position: --")
        self._pos_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._pos_label)

        # 缩放显示
        self._zoom_label = QLabel("Zoom: 100%")
        self._zoom_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._zoom_label)

    def set_gpu_status(self, text: str):
        self._gpu_label.setText(text)

    def set_fps(self, fps: float):
        self._fps_label.setText(f"{fps:.0f} FPS")

    def set_position(self, x: float, y: float):
        self._pos_label.setText(f"Position: ({x:.0f}, {y:.0f})")

    def set_zoom(self, zoom: float):
        self._zoom_label.setText(f"Zoom: {zoom * 100:.0f}%")

    def clear_position(self):
        self._pos_label.setText("Position: --")


class MainWindow(QMainWindow):
    """主窗口"""

    MIN_WIDTH = 900
    MIN_HEIGHT = 600

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        # 无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1200, 800)
        self.setWindowTitle("Roco Navigator")

        # 主背景
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG_PRIMARY};
            }}
        """)

        # 构建 UI
        self._setup_ui()

        # GPU 状态
        self._update_gpu_status()

        # 居中显示
        self._center_on_screen()

        logger.info("Main window initialized")

    def _setup_ui(self):
        """构建 UI 布局"""
        # 中央容器
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG_PRIMARY}; border-radius: 16px;")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 标题栏 ----
        self._title_bar = TitleBar(self, title="Roco Navigator")
        main_layout.addWidget(self._title_bar)

        # ---- 内容区域 ----
        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_PRIMARY};")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(12)

        # 侧边栏
        self._sidebar = Sidebar()
        self._connect_sidebar_signals()
        content_layout.addWidget(self._sidebar)

        # 地图画布
        self._map_canvas = MapCanvas()
        self._map_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self._map_canvas, stretch=1)

        main_layout.addWidget(content, stretch=1)

        # ---- 状态栏 ----
        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

    def _connect_sidebar_signals(self):
        """连接侧边栏信号"""
        self._sidebar.calibrate_clicked.connect(self._on_calibrate)
        self._sidebar.start_tracking_clicked.connect(self._on_start_tracking)
        self._sidebar.stop_tracking_clicked.connect(self._on_stop_tracking)
        self._sidebar.plan_route_clicked.connect(self._on_plan_route)
        self._sidebar.start_nav_clicked.connect(self._on_start_nav)
        self._sidebar.stop_nav_clicked.connect(self._on_stop_nav)
        self._sidebar.update_data_clicked.connect(self._on_update_data)
        self._sidebar.toggle_overlay_clicked.connect(self._on_toggle_overlay)
        self._sidebar.settings_clicked.connect(self._on_settings)

    def _update_gpu_status(self):
        """更新 GPU 状态显示"""
        gpu = GPUManager()
        if gpu.check_gpu_available():
            if self._settings.get("performance.use_gpu", False):
                self._status_bar.set_gpu_status(f"GPU Mode (CUDA)")
            else:
                self._status_bar.set_gpu_status("GPU Available (Disabled)")
        else:
            self._status_bar.set_gpu_status("CPU Mode")

    def _center_on_screen(self):
        """居中显示窗口"""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2 + screen_geo.x()
            y = (screen_geo.height() - self.height()) // 2 + screen_geo.y()
            self.move(x, y)

    # ==================== Public API ====================

    @property
    def map_canvas(self) -> MapCanvas:
        return self._map_canvas

    @property
    def sidebar(self) -> Sidebar:
        return self._sidebar

    @property
    def title_bar(self) -> TitleBar:
        return self._title_bar

    @property
    def status_bar_widget(self) -> StatusBarWidget:
        return self._status_bar

    # ==================== Sidebar callbacks (stubs for later stages) ====================

    def _on_calibrate(self):
        logger.info("Calibrate minimap requested")
        # TODO: Stage 2 - minimap calibration dialog

    def _on_start_tracking(self):
        logger.info("Start tracking requested")
        self._title_bar.set_status("tracking")
        self._title_bar.set_status_text("Tracking")
        # TODO: Stage 4 - start position tracker

    def _on_stop_tracking(self):
        logger.info("Stop tracking requested")
        self._title_bar.set_status("idle")
        self._title_bar.set_status_text("")
        # TODO: Stage 4 - stop position tracker

    def _on_plan_route(self):
        logger.info("Plan route requested")
        # TODO: Stage 6 - route planning

    def _on_start_nav(self):
        logger.info("Start navigation requested")
        self._title_bar.set_status("active")
        self._title_bar.set_status_text("Navigating")
        # TODO: Stage 7 - start navigation

    def _on_stop_nav(self):
        logger.info("Stop navigation requested")
        self._title_bar.set_status("idle")
        self._title_bar.set_status_text("")
        # TODO: Stage 7 - stop navigation

    def _on_update_data(self):
        logger.info("Update data from WIKI requested")
        # TODO: Stage 10 - WIKI data update

    def _on_toggle_overlay(self, enabled: bool):
        logger.info(f"Overlay HUD {'enabled' if enabled else 'disabled'}")
        # TODO: Stage 8 - toggle overlay HUD

    def _on_settings(self):
        logger.info("Settings requested")
        # TODO: Stage 9 - settings dialog

    # ==================== Window resize handles ====================

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        zoom = getattr(self._map_canvas, '_zoom', 1.0)
        self._status_bar.set_zoom(zoom)
