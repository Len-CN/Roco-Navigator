"""
主窗口

组装标题栏、侧边栏、地图画布等组件。
集成追踪、导航、HUD、数据更新等所有核心模块。
无边框窗口 + 新拟物派设计风格。
"""

import logging
import os
import sys
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox, QFileDialog, QInputDialog,
    QApplication, QSizePolicy, QFrame, QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QProcess
from PyQt5.QtGui import QColor, QResizeEvent, QPainter, QPainterPath

from ..config.settings import Settings
from .widgets.title_bar import TitleBar
from .widgets.sidebar import Sidebar
from .widgets.route_drawer import RouteDrawer
from .map_canvas import MapCanvas
from .overlay_hud import OverlayHUD
from .widgets.neumorphic import (
    BG_PRIMARY, BG_SECONDARY, TEXT_SECONDARY
)
# Core modules
from ..core.screen_capture import ScreenCapture
from ..core.minimap_detector import MinimapDetector
from ..core.position_tracker import PositionTracker, TrackingState, TrackingConfig
from ..core.pathfinding import PathPlanner, total_distance
from ..core.navigation import Navigator, NavigationState

# Data modules
from ..data.map_manager import MapManager
from ..data.resource_manager import ResourceManager
from ..data.route_manager import RouteManager, Route
from ..data.wiki_updater import WikiUpdater

logger = logging.getLogger(__name__)


# ==================== Worker thread for WIKI update ====================

class WikiUpdateWorker(QThread):
    """WIKI 更新后台线程"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, updater: WikiUpdater, task: str = "points"):
        """
        Args:
            updater: WikiUpdater instance
            task: "points" for point data, "map" for map tiles
        """
        super().__init__()
        self._updater = updater
        self._task = task

    def run(self):
        cb = lambda pct, text: self.progress.emit(pct, text)
        if self._task == "map":
            success, msg = self._updater.download_map(zoom=7, progress_callback=cb)
        else:
            success, msg = self._updater.update_points(progress_callback=cb)
        self.finished.emit(success, msg)


class RouteWorker(QThread):
    """路线规划后台线程

    finished payload: (RoutePlan, distance, names)
    """
    finished = pyqtSignal(object, float, list)
    failed = pyqtSignal(str)

    def __init__(self, planner, start_pos, resources, strategy,
                 teleport_hubs=None, end=None, teleport_cost=0.0):
        super().__init__()
        self._planner = planner
        self._start = start_pos or (resources[0]["x"], resources[0]["y"])
        self._resources = resources
        self._strategy = strategy
        self._teleport_hubs = list(teleport_hubs) if teleport_hubs else []
        self._end = end
        self._teleport_cost = teleport_cost

    @property
    def teleport_hubs(self):
        """让回调用同一份 hubs 比对，避免重复计算引发的浮点漂移误差。"""
        return self._teleport_hubs

    def run(self):
        try:
            targets = [(r["x"], r["y"]) for r in self._resources]
            names = [r.get("name", "") for r in self._resources]
            plan = self._planner.plan_route(
                self._start, targets, self._strategy,
                teleport_hubs=self._teleport_hubs,
                teleport_cost=self._teleport_cost,
                end=self._end,
            )
            self.finished.emit(plan, plan.total_cost, names)
        except Exception as e:
            logger.exception("Route planning failed")
            self.failed.emit(str(e))


# ==================== 状态栏 ====================

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

        self._gpu_label = QLabel("CPU 模式")
        self._gpu_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._gpu_label)

        layout.addStretch()

        self._fps_label = QLabel("-- FPS")
        self._fps_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._fps_label)

        self._state_label = QLabel("空闲")
        self._state_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._state_label)

        self._pos_label = QLabel("位置: --")
        self._pos_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._pos_label)

        self._zoom_label = QLabel("缩放: 100%")
        self._zoom_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._zoom_label)

    def set_gpu_status(self, text: str):
        self._gpu_label.setText(text)

    def set_fps(self, fps: float):
        self._fps_label.setText(f"{fps:.0f} FPS")

    def set_state(self, text: str):
        self._state_label.setText(text)

    def set_position(self, x: float, y: float):
        self._pos_label.setText(f"位置: ({x:.0f}, {y:.0f})")

    def set_zoom(self, zoom: float):
        self._zoom_label.setText(f"缩放: {zoom * 100:.0f}%")

    def clear_position(self):
        self._pos_label.setText("位置: --")


# ==================== 圆角中央容器 ====================

class RoundedCentralWidget(QWidget):
    """圆角中央容器 - 手动绘制圆角背景，防止子控件突破圆角"""

    def __init__(self, bg_color: str, radius: int = 16, parent=None):
        super().__init__(parent)
        self._bg_color = QColor(bg_color)
        self._radius = radius
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        painter.setClipPath(path)
        painter.fillPath(path, self._bg_color)


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    """主窗口 - 集成所有模块"""

    MIN_WIDTH = 900
    MIN_HEIGHT = 600

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        # 无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1200, 800)
        self.setWindowTitle("洛克导航")
        self.setStyleSheet("QMainWindow { background: transparent; }")

        # ---- 初始化核心模块 ----
        self._screen_capture = ScreenCapture()
        self._map_manager = MapManager()
        self._resource_manager = ResourceManager()
        self._route_manager = RouteManager()
        self._wiki_updater = WikiUpdater()

        # Auto-detect GPU (CUDA OpenCV)
        try:
            import cv2 as _cv2
            use_gpu = hasattr(_cv2, 'cuda') and _cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            use_gpu = False
        self._minimap_detector = MinimapDetector(
            use_clahe=settings.get("minimap_detection.use_clahe", True),
            use_ring_mask=settings.get("minimap_detection.use_ring_mask", True),
            use_gpu=use_gpu,
            sift_ratio=settings.get("minimap_detection.sift_ratio_threshold", 0.9),
            min_matches=settings.get("minimap_detection.min_good_matches", 5),
            ring_inner=0.15,
        )
        self._tracker = PositionTracker(
            self._screen_capture,
            self._minimap_detector,
            self._map_manager,
            TrackingConfig(
                update_interval_ms=settings.get("tracking.update_interval", 100),
                teleport_threshold=settings.get("tracking.teleport_threshold", 200),
            )
        )
        self._path_planner = PathPlanner(
            use_2opt=settings.get("navigation.use_2opt", True)
        )
        self._navigator = Navigator(
            arrival_distance=settings.get("navigation.arrival_distance", 20),
        )

        # 加载数据
        self._resource_manager.load()
        self._route_manager.load()
        self._current_route_id: str = ""
        self._route_dirty: bool = False
        self._route_editing: bool = False
        self._route_snapshot = []

        # ---- 构建 UI ----
        self._setup_ui()

        # ---- 悬浮窗 HUD ----
        hud_size = settings.get("ui.overlay_size", {"width": 320, "height": 400})
        hud_shape = settings.get("ui.hud_shape", "rounded_rect")
        self._overlay_hud = OverlayHUD(
            size="中",
            custom_w=hud_size.get("width", 0),
            custom_h=hud_size.get("height", 0),
            shape=hud_shape,
        )
        if settings.get("ui.overlay_enabled", True):
            self._overlay_hud.show()
        self._sidebar.set_overlay_enabled(settings.get("ui.overlay_enabled", True))
        self._apply_display_options()
        self._overlay_hud.closed.connect(self._on_overlay_closed)
        self._overlay_hud.crop_size_changed.connect(self._on_hud_crop_size_changed)
        self._overlay_hud.size_changed.connect(self._on_hud_size_changed)
        self._overlay_hud.shape_changed.connect(self._on_hud_shape_changed)

        # ---- 定时器 ----
        self._tracking_timer = QTimer(self)
        self._tracking_timer.timeout.connect(self._on_tracking_tick)

        # ---- 回调 ----
        self._tracker.set_on_position_update(self._on_position_updated)
        self._tracker.set_on_state_change(self._on_tracking_state_changed)
        self._navigator.set_on_target_reached(self._on_target_reached)
        self._navigator.set_on_navigation_complete(self._on_navigation_complete)

        # GPU 状态
        self._update_gpu_status()
        self._update_data_info()
        self._refresh_route_library()
        self._update_route_info()
        self._center_on_screen()

        # ---- 依赖安装进程 (managed at MainWindow level for persistence) ----
        self._dep_install_process: Optional[QProcess] = None
        self._dep_install_log: str = ""
        self._dep_install_running: bool = False
        self._dep_needs_restart: bool = False
        self._dep_opencv_switched: str = ""  # "cpu" or "cuda" after opencv switch

        # Enable AI mode if configured
        detection_mode = settings.get("tracking.detection_mode", "sift")
        self._minimap_detector.set_detection_mode(detection_mode)

        logger.info("Main window initialized with all modules integrated")

    def _setup_ui(self):
        """构建 UI 布局"""
        central = RoundedCentralWidget(BG_PRIMARY, radius=16)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏
        self._title_bar = TitleBar(self, title="洛克导航")
        main_layout.addWidget(self._title_bar)

        # 内容区域
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(12)

        self._side_stack = QStackedWidget()
        self._side_stack.setFixedWidth(270)
        self._side_stack.setStyleSheet("QStackedWidget { background: transparent; }")

        self._sidebar = Sidebar()
        self._connect_sidebar_signals()
        self._side_stack.addWidget(self._sidebar)

        self._route_drawer = RouteDrawer()
        self._connect_route_drawer_signals()
        self._side_stack.addWidget(self._route_drawer)
        content_layout.addWidget(self._side_stack)

        self._map_canvas = MapCanvas()
        self._map_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._map_canvas.position_clicked.connect(self._on_map_clicked)
        self._map_canvas.region_selected.connect(self._on_region_selected)
        self._map_canvas.waypoint_skip_requested.connect(self._on_waypoint_skip_requested)
        self._map_canvas.route_points_changed.connect(self._on_route_points_changed)
        content_layout.addWidget(self._map_canvas, stretch=1)

        main_layout.addWidget(content, stretch=1)

        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

    def _connect_sidebar_signals(self):
        self._sidebar.calibrate_clicked.connect(self._on_calibrate)
        self._sidebar.start_tracking_clicked.connect(self._on_start_tracking)
        self._sidebar.stop_tracking_clicked.connect(self._on_stop_tracking)
        self._sidebar.start_nav_clicked.connect(self._on_start_nav)
        self._sidebar.stop_nav_clicked.connect(self._on_stop_nav)
        self._sidebar.update_points_clicked.connect(self._on_update_points)
        self._sidebar.update_map_clicked.connect(self._on_update_map)
        self._sidebar.toggle_overlay_clicked.connect(self._on_toggle_overlay)
        self._sidebar.overlay_passthrough_clicked.connect(self._on_toggle_overlay_passthrough)
        self._sidebar.settings_clicked.connect(self._on_settings)
        self._sidebar.filter_type_changed.connect(self._on_filter_type_changed)
        self._sidebar.plan_route_for_type.connect(self._on_plan_route_for_type)
        self._sidebar.select_region_for_route.connect(self._on_select_region_for_route)
        self._sidebar.route_drawer_clicked.connect(self._toggle_route_drawer)

    def _connect_route_drawer_signals(self):
        self._route_drawer.route_selected_changed.connect(self._on_route_selected_changed)
        self._route_drawer.route_draw_clicked.connect(self._on_route_draw)
        self._route_drawer.route_finish_clicked.connect(self._on_route_finish)
        self._route_drawer.route_cancel_clicked.connect(self._on_route_cancel)
        self._route_drawer.route_save_clicked.connect(self._on_route_save)
        self._route_drawer.route_load_clicked.connect(self._on_route_load)
        self._route_drawer.route_rename_clicked.connect(self._on_route_rename)
        self._route_drawer.route_duplicate_clicked.connect(self._on_route_duplicate)
        self._route_drawer.route_delete_clicked.connect(self._on_route_delete)
        self._route_drawer.route_import_clicked.connect(self._on_route_import)
        self._route_drawer.route_export_current_clicked.connect(self._on_route_export_current)
        self._route_drawer.route_export_all_clicked.connect(self._on_route_export_all)
        self._route_drawer.closed.connect(self._show_main_sidebar)

    def _toggle_route_drawer(self):
        if self._side_stack.currentWidget() is self._route_drawer:
            self._show_main_sidebar()
        else:
            self._show_route_library()

    def _show_route_library(self):
        self._refresh_route_library()
        self._update_route_info()
        self._side_stack.setCurrentWidget(self._route_drawer)

    def _show_main_sidebar(self):
        self._side_stack.setCurrentWidget(self._sidebar)

    # ==================== Tracking ====================

    def _on_calibrate(self):
        """打开小地图校准选择器"""
        logger.info("Calibrate minimap requested")
        from .widgets.minimap_selector import MinimapSelector

        region = self._settings.get("minimap.region", {"x": 100, "y": 100, "width": 200, "height": 200})
        self._selector = MinimapSelector(
            initial_x=region.get("x", 100),
            initial_y=region.get("y", 100),
            initial_size=region.get("width", 200),
        )
        self._selector.selection_confirmed.connect(self._on_calibration_done)
        self._selector.show()

    def _on_calibration_done(self, region: dict):
        """校准完成"""
        self._settings.set("minimap.region", region)
        self._settings.set("minimap.calibrated", True)
        self._settings.save()
        self._tracker.set_minimap_region(region)
        logger.info("Minimap calibrated: %s", region)

    def _on_start_tracking(self):
        """开始追踪"""
        region = self._settings.get("minimap.region")
        if not region or not self._settings.get("minimap.calibrated", False):
            QMessageBox.warning(self, "警告",
                                "请先校准小地图。\n"
                                "点击\"校准小地图\"选择小地图区域。")
            self._sidebar.set_tracking_active(False)
            return

        if not self._map_manager.is_loaded:
            QMessageBox.warning(self, "警告",
                                "未加载地图。请先下载地图。\n"
                                "点击\"更新地图\"从 WIKI 下载。")
            self._sidebar.set_tracking_active(False)
            return

        self._tracker.set_minimap_region(region)
        self._tracker.start()

        interval = self._settings.get("tracking.update_interval", 100)
        self._tracking_timer.start(interval)

        self._title_bar.set_status("tracking")
        self._title_bar.set_status_text("追踪中")
        logger.info("Tracking started")

    def _on_stop_tracking(self):
        """停止追踪"""
        self._tracking_timer.stop()
        self._tracker.stop()
        self._title_bar.set_status("idle")
        self._title_bar.set_status_text("")
        self._status_bar.clear_position()
        logger.info("Tracking stopped")

    def _on_tracking_tick(self):
        """追踪定时更新"""
        status = self._tracker.update()
        if status is None:
            return

        self._status_bar.set_fps(status.fps)
        self._status_bar.set_state(status.state.value)

        if status.position:
            self._status_bar.set_position(*status.position)
            self._map_canvas.set_player_position(
                status.position[0], status.position[1], status.direction
            )

            # 更新导航
            if self._navigator.is_active:
                nav_info = self._navigator.update(*status.position)
                self._update_hud_from_nav(status, nav_info)
                self._sidebar.set_nav_progress(
                    int(nav_info.progress * 100),
                    f"{nav_info.current_target_index}/{nav_info.total_targets} - "
                    f"{nav_info.distance_to_target:.0f}px"
                )

    def _on_position_updated(self, x: float, y: float, direction: float, confidence: float):
        """位置更新回调"""
        self._map_canvas.set_player_position(x, y, direction)

    def _on_tracking_state_changed(self, state: TrackingState):
        """追踪状态变化"""
        state_map = {
            TrackingState.IDLE: ("idle", "空闲"),
            TrackingState.GLOBAL_SCAN: ("tracking", "扫描中..."),
            TrackingState.PRECISE_TRACK: ("active", "追踪中"),
            TrackingState.INERTIA_NAV: ("warning", "惯性导航"),
            TrackingState.LOST: ("error", "丢失"),
        }
        status, text = state_map.get(state, ("idle", ""))
        self._title_bar.set_status(status)
        self._title_bar.set_status_text(text)
        self._sidebar.set_tracking_status(status, text)

    # ==================== Navigation ====================

    def _on_filter_type_changed(self, selected_names):
        """点位类型筛选 - selected_names is a set of mark_type_name strings, or empty for all"""
        display = self._resource_manager.to_display_list(
            mark_type_names=selected_names if selected_names else None
        )
        self._map_canvas.set_resources(display)
        logger.info("Filter changed: %d selected (%d points)",
                     len(selected_names) if selected_names else 0, len(display))

    def _get_hubs(self):
        """获取传送中继点坐标列表（按 settings 控制启停）"""
        from ..core.pathfinding import TELEPORT_HUB_TYPES
        if not self._settings.get("navigation.use_teleport_hubs", True):
            return []
        return [(r.x, r.y) for r in self._resource_manager.get_all()
                if r.mark_type_name in TELEPORT_HUB_TYPES]

    def _get_endpoint_mode(self):
        """从 settings 读终点策略。返回 'open' / 'loop'"""
        return self._settings.get("navigation.route_endpoint", "open")

    def _build_route_kwargs(self, start):
        """从 settings + ResourceManager + sidebar 抽取规划参数。

        Args:
            start: 实际使用的起点 (x, y)。环形模式下 end == start，必须传入
                   实际起点（不能依赖 tracker.position，可能为 None）。
        Returns:
            (teleport_hubs, end, teleport_cost)
        """
        hubs = self._get_hubs()
        endpoint = self._get_endpoint_mode()
        end = tuple(start) if endpoint == "loop" else None
        teleport_cost = float(self._settings.get("navigation.teleport_cost_px", 150))
        return hubs, end, teleport_cost

    @staticmethod
    def _route_start_and_targets(tracker_position, resources):
        """计算路线起点和目标列表，避免 fallback 起点重复作为目标。"""
        if not resources:
            return None, []
        if tracker_position is not None:
            return tracker_position, resources
        return (resources[0]["x"], resources[0]["y"]), resources[1:]

    def _on_plan_route_for_type(self, selected_names):
        """为选中类型的资源规划路线 - selected_names is a set of mark_type_name strings"""
        if selected_names:
            resources = self._resource_manager.to_display_list(mark_type_names=selected_names)
        else:
            resources = self._resource_manager.to_display_list()

        if not resources:
            QMessageBox.information(self, "提示", "当前筛选条件下没有资源点。")
            return

        # 防重入：上一次规划还在跑就忽略
        if (getattr(self, "_route_worker", None) is not None
                and self._route_worker.isRunning()):
            logger.info("Plan ignored: previous worker still running")
            return

        self._sidebar.set_nav_progress(0, "正在规划路线...")

        # 显式计算 start，确保环形 end == start（即使 tracker 未追踪）
        start, resources = self._route_start_and_targets(
            self._tracker.position, resources)
        if not resources:
            QMessageBox.information(self, "提示", "当前筛选条件下没有可导航的目标点。")
            self._sidebar.set_nav_progress(0, "规划取消")
            return

        max_points = self._settings.get("navigation.max_route_points", 500)
        if len(resources) > max_points:
            QMessageBox.information(self, "提示",
                                    f"当前筛选有 {len(resources)} 个目标点，超过上限 {max_points}。\n"
                                    "请选择具体的资源类型，或在设置→性能中调整上限。")
            return
        hubs, end, teleport_cost = self._build_route_kwargs(start)
        logger.info("Plan kwargs: start=%s end=%s endpoint=%s hubs=%d cost=%s",
                    start, end, self._get_endpoint_mode(), len(hubs), teleport_cost)
        # Run in background
        self._route_worker = RouteWorker(
            self._path_planner, start, resources,
            self._settings.get("navigation.route_strategy", "nearest"),
            teleport_hubs=hubs, end=end, teleport_cost=teleport_cost
        )
        self._route_worker.finished.connect(self._on_route_planned)
        self._route_worker.failed.connect(self._on_route_plan_failed)
        self._route_worker.start()

    def _on_route_planned(self, plan, dist, names):
        """路线规划完成回调

        plan: RoutePlan (含 points / teleport_segments / total_cost / used_strategy)
        """
        points = list(plan.points)
        teleport_segments = plan.teleport_segments
        if not points or len(points) < 2:
            self._sidebar.set_nav_progress(0, "规划失败")
            self._map_canvas.clear_route()
            self._map_canvas.clear_selected_region()
            return

        selected = self._sidebar._get_selected_mark_type_names()
        type_name = ", ".join(sorted(selected)) if selected else "全部"
        self._current_route_id = ""
        self._route_dirty = True
        self._route_editing = False
        self._route_snapshot = []
        # 优先用 worker 持有的 hubs（与 plan_route 同一份引用，避免浮点失配）
        worker = getattr(self, "_route_worker", None)
        hubs = list(worker.teleport_hubs) if worker is not None else self._get_hubs()
        hub_set = set(hubs)
        hub_indices = {i for i, pt in enumerate(points) if pt in hub_set}
        self._map_canvas.set_route([(p[0], p[1]) for p in points],
                                   teleport_segments=teleport_segments,
                                   hub_indices=hub_indices)
        self._map_canvas.finish_route_editing()
        self._map_canvas.clear_selected_region()
        self._route_drawer.set_current_route_id("")
        self._refresh_route_library()
        self._update_route_info()
        tp_hint = f", {len(teleport_segments)} 段瞬移" if teleport_segments else ""
        self._sidebar.set_nav_progress(
            0, f"草稿路线: {type_name}, {len(points)-1} 个目标, {dist:.0f}px{tp_hint}")
        logger.info("Route planned: %d targets, %d teleport segs, %d hubs, %.0f cost",
                    len(points) - 1, len(teleport_segments), len(hub_indices), dist)

    def _on_route_plan_failed(self, message: str):
        self._sidebar.set_nav_progress(0, f"规划失败: {message[:80]}")
        self._map_canvas.clear_route()
        self._map_canvas.clear_selected_region()
        logger.error("Route planning failed: %s", message)

    def _on_start_nav(self):
        """开始导航"""
        if len(self._map_canvas._route_points) < 2:
            QMessageBox.information(self, "提示", "路线至少需要 2 个点。请先规划路线。")
            self._sidebar.set_nav_active(False)
            return

        route = [(p.x(), p.y()) for p in self._map_canvas._route_points]
        target_names = self._build_nav_target_names(route)
        self._navigator.start(route, target_names=target_names)
        self._map_canvas.update_route_progress(
            current_index=self._navigator.current_index,
            visited=self._navigator.visited_indices,
        )

        self._title_bar.set_status("active")
        self._title_bar.set_status_text("导航中")
        logger.info("Navigation started")

    def _on_stop_nav(self):
        """停止导航"""
        if not self._navigator.is_active:
            self._sidebar.set_nav_active(False)
            self._sidebar.set_nav_progress(0, "导航未启动")
            return
        self._navigator.stop()
        self._title_bar.set_status("tracking" if self._tracker.is_running else "idle")
        self._title_bar.set_status_text("追踪中" if self._tracker.is_running else "")
        self._sidebar.set_nav_progress(0, "导航已停止")

    def _on_target_reached(self, index: int, target):
        logger.info("Target %d reached: (%.0f, %.0f)", index, target[0], target[1])
        # 仅更新进度，保留瞬移段虚线与 hub 图标
        self._map_canvas.update_route_progress(
            current_index=index + 1,
            visited=self._navigator.visited_indices,
        )

    def _on_waypoint_skip_requested(self, index: int):
        """用户双击路线点，跳转到该点（之前所有未到达目标标记为已到达）"""
        if not self._navigator.is_active:
            return
        self._navigator.jump_to(index)
        self._map_canvas.update_route_progress(
            current_index=self._navigator.current_index,
            visited=self._navigator.visited_indices,
        )

    def _on_navigation_complete(self):
        logger.info("Navigation complete!")
        self._sidebar.set_nav_active(False)
        self._sidebar.set_nav_progress(100, "导航完成！")
        self._title_bar.set_status("active")
        self._title_bar.set_status_text("已完成")

    # ==================== Route Library ====================

    def _refresh_route_library(self):
        self._route_drawer.set_routes(self._route_manager.get_all(), self._current_route_id)

    def _current_route_points(self):
        return self._map_canvas.get_route_points()

    def _current_route_distance(self):
        points = self._current_route_points()
        return total_distance(points) if len(points) >= 2 else 0.0

    def _update_route_info(self):
        point_count = len(self._current_route_points())
        distance = self._current_route_distance()
        self._route_drawer.set_route_info(
            point_count,
            distance,
            dirty=self._route_dirty,
            editing=self._route_editing,
        )
        self._route_drawer.set_route_editing_active(self._route_editing)
        self._sidebar.set_route_summary(
            point_count,
            distance,
            dirty=self._route_dirty,
            editing=self._route_editing,
        )

    def _on_route_points_changed(self, _points):
        self._route_dirty = True
        if self._navigator.is_active:
            self._navigator.stop()
        self._update_route_info()

    def _on_route_selected_changed(self, route_id):
        logger.debug("Route selected in library: %s", route_id)

    def _confirm_discard_dirty(self) -> bool:
        if not self._route_dirty:
            return True
        reply = QMessageBox.question(
            self, "未保存路线",
            "当前路线还没有保存，是否放弃这些修改？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _load_route_to_canvas(self, route: Route):
        self._current_route_id = route.id
        self._route_dirty = False
        self._route_editing = False
        self._route_snapshot = []
        if self._navigator.is_active:
            self._navigator.stop()
        self._map_canvas.finish_route_editing()
        self._map_canvas.set_route(route.points)
        self._route_drawer.set_current_route_id(route.id)
        self._sidebar.set_nav_progress(0, f"已加载路线: {route.name}")
        self._update_route_info()

    def _on_route_draw(self):
        if not self._confirm_discard_dirty():
            return
        self._route_dirty = False
        self._route_editing = True
        if self._navigator.is_active:
            self._navigator.stop()
        current_points = self._current_route_points()
        if current_points:
            self._route_snapshot = list(current_points)
            self._map_canvas.start_route_editing()
            self._route_drawer.set_draw_hint("编辑中: 拖动点调整路线，点击线段插入点，Delete 删除选中的点。")
            self._sidebar.set_nav_progress(0, "正在编辑路线")
        else:
            self._current_route_id = ""
            self._route_snapshot = []
            self._route_drawer.set_current_route_id("")
            self._map_canvas.start_route_drawing(clear=True)
            self._route_drawer.set_draw_hint("绘制中: 在地图上左键逐点添加路线，至少添加 2 个点后可完成并保存。")
            self._sidebar.set_nav_progress(0, "正在绘制路线")
        self._update_route_info()

    def _on_route_finish(self):
        self._route_editing = False
        self._map_canvas.finish_route_editing()
        self._route_drawer.set_draw_hint("路线编辑已完成，可保存到路线库，或返回侧边栏开始导航。")
        self._sidebar.set_nav_progress(0, "路线编辑已完成，可保存或开始导航")
        self._update_route_info()

    def _on_route_cancel(self):
        self._route_editing = False
        self._map_canvas.finish_route_editing()
        if self._route_snapshot:
            self._map_canvas.set_route(self._route_snapshot)
            self._route_snapshot = []
            self._route_dirty = False
        elif not self._current_route_id:
            self._map_canvas.clear_route()
            self._route_dirty = False
        self._route_drawer.set_draw_hint("已取消编辑。点击“绘制 / 编辑”可重新开始。")
        self._sidebar.set_nav_progress(0, "已取消路线编辑")
        self._update_route_info()

    def _on_route_save(self):
        points = self._current_route_points()
        if len(points) < 2:
            QMessageBox.information(self, "提示", "路线至少需要 2 个点。")
            return

        route = self._route_manager.get_by_id(self._current_route_id) if self._current_route_id else None
        if route is None:
            name, ok = QInputDialog.getText(self, "保存路线", "路线名称:")
            if not ok:
                return
            name = name.strip() or "未命名路线"
            route = Route(
                id="",
                name=name,
                points=points,
                total_distance=total_distance(points),
                strategy="custom",
                map_id="default",
            )
            self._route_manager.add(route)
            self._current_route_id = route.id
        else:
            route.points = points
            route.total_distance = total_distance(points)
            if route.strategy.startswith("auto"):
                route.strategy = "custom"
            self._route_manager.update(route)

        if not self._route_manager.save():
            QMessageBox.warning(self, "保存失败", "路线文件保存失败，请检查文件权限。")
            return

        self._route_dirty = False
        self._route_editing = False
        self._route_snapshot = []
        self._map_canvas.finish_route_editing()
        self._refresh_route_library()
        self._route_drawer.set_current_route_id(self._current_route_id)
        self._route_drawer.set_draw_hint("路线已保存。可以继续编辑、加载其他路线，或返回侧边栏开始导航。")
        self._sidebar.set_nav_progress(0, f"已保存路线: {route.name}")
        self._update_route_info()

    def _on_route_load(self):
        route_id = self._route_drawer.selected_route_id()
        if not route_id:
            QMessageBox.information(self, "提示", "请先在路线库中选择路线。")
            return
        if not self._confirm_discard_dirty():
            return
        route = self._route_manager.get_by_id(route_id)
        if route is None:
            QMessageBox.warning(self, "加载失败", "找不到选中的路线。")
            self._refresh_route_library()
            return
        self._load_route_to_canvas(route)

    def _on_route_rename(self):
        route_id = self._route_drawer.selected_route_id() or self._current_route_id
        route = self._route_manager.get_by_id(route_id)
        if route is None:
            QMessageBox.information(self, "提示", "请先选择已保存的路线。")
            return
        name, ok = QInputDialog.getText(self, "重命名路线", "路线名称:", text=route.name)
        if not ok:
            return
        route.name = name.strip() or route.name
        self._route_manager.update(route)
        self._route_manager.save()
        self._refresh_route_library()
        self._route_drawer.set_current_route_id(route.id)

    def _on_route_duplicate(self):
        route_id = self._route_drawer.selected_route_id() or self._current_route_id
        route = self._route_manager.duplicate(route_id)
        if route is None:
            QMessageBox.information(self, "提示", "请先选择已保存的路线。")
            return
        self._route_manager.save()
        self._refresh_route_library()
        self._load_route_to_canvas(route)

    def _on_route_delete(self):
        route_id = self._route_drawer.selected_route_id() or self._current_route_id
        route = self._route_manager.get_by_id(route_id)
        if route is None:
            QMessageBox.information(self, "提示", "请先选择已保存的路线。")
            return
        reply = QMessageBox.question(
            self, "删除路线",
            f"确定删除路线“{route.name}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._route_manager.delete(route.id)
        self._route_manager.save()
        if self._current_route_id == route.id:
            self._current_route_id = ""
            self._route_dirty = False
            self._route_editing = False
            self._map_canvas.finish_route_editing()
            self._map_canvas.clear_route()
        self._refresh_route_library()
        self._update_route_info()

    def _on_route_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入路线", "", "路线 JSON (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        imported = self._route_manager.import_routes(path)
        if not imported:
            QMessageBox.warning(self, "导入失败", "没有导入任何路线。")
            return
        self._route_manager.save()
        self._refresh_route_library()
        self._load_route_to_canvas(imported[0])
        QMessageBox.information(self, "导入完成", f"已导入 {len(imported)} 条路线。")

    def _on_route_export_current(self):
        points = self._current_route_points()
        route = None
        saved_route = self._route_manager.get_by_id(self._current_route_id)
        if len(points) >= 2:
            route = Route(
                id=self._current_route_id or "draft",
                name=saved_route.name if saved_route else "未保存路线",
                points=points,
                total_distance=total_distance(points),
                strategy=saved_route.strategy if saved_route else "custom",
                map_id=saved_route.map_id if saved_route else "default",
                created=saved_route.created if saved_route else "",
                updated=saved_route.updated if saved_route else "",
                description=saved_route.description if saved_route else "",
            )
        if route is None:
            QMessageBox.information(self, "提示", "暂无可导出的当前路线。")
            return

        default_name = self._safe_export_filename(route.name)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前路线", default_name, "路线 JSON (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        if self._route_manager.export_route(route, path):
            QMessageBox.information(self, "导出完成", "当前路线已导出。")
        else:
            QMessageBox.warning(self, "导出失败", "路线导出失败。")

    def _on_route_export_all(self):
        if self._route_manager.count <= 0:
            QMessageBox.information(self, "提示", "路线库中暂无路线。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出全部路线", "roco_routes.json", "路线 JSON (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        if self._route_manager.export_all(path):
            QMessageBox.information(self, "导出完成", "全部路线已导出。")
        else:
            QMessageBox.warning(self, "导出失败", "路线导出失败。")

    @staticmethod
    def _safe_export_filename(name: str) -> str:
        safe = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in (name or "route"))
        return f"{safe.strip() or 'route'}.json"

    def _build_nav_target_names(self, route):
        display_list = self._resource_manager.to_display_list()
        res_lookup = {
            (round(res["x"]), round(res["y"])): res.get("name", "")
            for res in display_list
        }
        names = []
        for i, pt in enumerate(route):
            if i == 0:
                names.append("起点")
                continue
            name = res_lookup.get((round(pt[0]), round(pt[1])))
            names.append(name or f"点位 {i}")
        return names

    def _update_hud_from_nav(self, tracking_status, nav_info):
        """更新 HUD 显示"""
        if not self._overlay_hud.isVisible():
            return

        pos = tracking_status.position
        if pos is None:
            return

        # 获取地图裁剪 (configurable crop size for zoom)
        hud_crop_size = self._settings.get("ui.hud_crop_size", 350)
        crop, rel = self._map_manager.get_map_crop_centered(pos[0], pos[1], hud_crop_size)
        if crop is None:
            return

        # 转换路线点为裁剪图相对坐标
        route_rel = []
        rel_x, rel_y = rel
        crop_h, crop_w = crop.shape[:2]
        for pt in self._navigator.route:
            rx = pt[0] - pos[0] + rel_x
            ry = pt[1] - pos[1] + rel_y
            route_rel.append((rx, ry))

        target_rel = None
        if nav_info.current_target:
            target_rel = (
                nav_info.current_target[0] - pos[0] + rel_x,
                nav_info.current_target[1] - pos[1] + rel_y,
            )

        # 只传递规划路线中的点位 (不传全部资源点)
        resource_rel = []
        if self._navigator.route:
            display_list = self._resource_manager.to_display_list()
            # 建立坐标→资源的快速查找 (四舍五入到整数避免浮点误差)
            res_lookup = {}
            for res in display_list:
                key = (round(res["x"]), round(res["y"]))
                res_lookup[key] = res
            # 只保留路线中的点位
            for pt in self._navigator.route:
                key = (round(pt[0]), round(pt[1]))
                res = res_lookup.get(key)
                rx = pt[0] - pos[0] + rel_x
                ry = pt[1] - pos[1] + rel_y
                if -10 <= rx <= crop_w + 10 and -10 <= ry <= crop_h + 10:
                    resource_rel.append({
                        "rx": rx, "ry": ry,
                        "type": res.get("type", "") if res else "",
                        "name": res.get("name", "") if res else "",
                        "mark_type": res.get("mark_type", 0) if res else 0,
                    })

        self._overlay_hud.update_navigation(
            map_crop=crop,
            player_rel=rel,
            player_direction=tracking_status.direction,
            route_rel=route_rel,
            target_rel=target_rel,
            target_name=nav_info.target_name,
            distance_val=nav_info.distance_to_target,
            eta=nav_info.eta_seconds,
            progress=nav_info.progress,
            current_idx=nav_info.current_target_index,
            total=nav_info.total_targets,
            direction_to_target=nav_info.direction_to_target,
            resource_rel_points=resource_rel,
            visited_indices=self._navigator.visited_indices,
            current_route_index=nav_info.current_target_index,
        )

    # ==================== Data ====================

    def _on_update_points(self):
        """WIKI 点位数据更新"""
        if self._wiki_updater.is_updating:
            QMessageBox.information(self, "提示", "更新正在进行中。")
            return

        self._sidebar.set_data_info("正在更新点位...")
        self._wiki_worker = WikiUpdateWorker(self._wiki_updater, task="points")
        self._wiki_worker.progress.connect(
            lambda pct, msg: self._sidebar.set_data_info(f"{pct}% - {msg}")
        )
        self._wiki_worker.finished.connect(self._on_points_update_done)
        self._wiki_worker.start()

    def _on_points_update_done(self, success: bool, message: str):
        if success:
            self._sidebar.set_data_info(message)
            logger.info("Points update: %s", message)
            # Reload resources from cache
            self._load_points_from_cache()
        else:
            self._sidebar.set_data_info(f"失败: {message}")
            logger.error("Points update failed: %s", message)

    def _on_update_map(self):
        """WIKI 地图下载"""
        if self._wiki_updater.is_updating:
            QMessageBox.information(self, "提示", "更新正在进行中。")
            return

        self._sidebar.set_data_info("正在下载地图...")
        self._wiki_worker = WikiUpdateWorker(self._wiki_updater, task="map")
        self._wiki_worker.progress.connect(
            lambda pct, msg: self._sidebar.set_data_info(f"{pct}% - {msg}")
        )
        self._wiki_worker.finished.connect(self._on_map_update_done)
        self._wiki_worker.start()

    def _on_map_update_done(self, success: bool, message: str):
        if success:
            self._sidebar.set_data_info(message)
            logger.info("Map update: %s", message)
            # Auto-load the downloaded map
            self._try_load_map()
        else:
            self._sidebar.set_data_info(f"失败: {message}")
            logger.error("Map update failed: %s", message)

    def _try_load_map(self):
        """尝试加载已下载的地图"""
        # Try zoom levels from high to low (优先 zoom 7 以获得更好的定位精度)
        for z in [7, 6, 8, 5, 4]:
            map_path = self._wiki_updater.get_map_path(z)
            if map_path:
                if self._map_manager.load_map(map_path, f"world_z{z}"):
                    self._map_canvas.load_map_image(map_path)
                    self._sidebar.set_data_info(
                        f"地图已加载: {self._map_manager.map_width}x{self._map_manager.map_height}"
                    )
                    logger.info("Map auto-loaded: %s", map_path)

                    # Pre-compute SIFT features for fast tracking
                    import cv2
                    map_bgr = cv2.imread(str(map_path))
                    if map_bgr is not None:
                        map_gray = cv2.cvtColor(map_bgr, cv2.COLOR_BGR2GRAY)
                        count = self._tracker.precompute_map_features(map_gray)
                        if count > 0:
                            logger.info("Pre-computed %d SIFT features for tracking", count)
                        else:
                            logger.warning("SIFT feature precomputation returned 0 features")

                    return True
        return False

    def _load_points_from_cache(self):
        """从缓存加载点位数据到 ResourceManager"""
        cache = self._wiki_updater.get_cached_data()
        if not cache:
            return

        from ..data.resource_manager import Resource

        points = cache.get("points", [])
        mark_type_map = {}
        for mt in cache.get("mark_types", []):
            mark_type_map[mt.get("mark_type", 0)] = mt

        self._resource_manager.clear()
        skipped = 0
        for pt in points:
            mt_id = pt.get("mark_type", 0)
            mt_info = mark_type_map.get(mt_id, {})
            # Skip orphaned points with no category info
            if not mt_info:
                skipped += 1
                continue
            # Convert Leaflet coords (lng, lat) to pixel coords
            lng = pt.get("x", 0)
            lat = pt.get("y", 0)
            px, py = self._wiki_updater.world_to_pixel(lng, lat)
            self._resource_manager.add(Resource(
                id=pt.get("id", ""),
                name=pt.get("name", mt_info.get("mark_type_name", "")),
                type=mt_info.get("type", ""),
                x=px,
                y=py,
                mark_type=mt_id,
                mark_type_name=mt_info.get("mark_type_name", ""),
                icon_url=mt_info.get("icon_url", ""),
                description=pt.get("desc", ""),
                source="wiki",
            ))
        if skipped:
            logger.info("Skipped %d points with unknown mark_type", skipped)

        count = self._resource_manager.count
        self._map_canvas.set_resources(self._resource_manager.to_display_list())

        # Load WIKI icons
        import os
        icons_dir = os.path.join(self._wiki_updater._icons_dir)
        self._map_canvas.load_resource_icons(icons_dir, cache.get("mark_types", []))

        # 共享图标缓存给 HUD
        self._overlay_hud.set_icon_cache(self._map_canvas._icon_cache)

        self._sidebar.set_data_info(f"已从 WIKI 加载 {count} 个点位")
        logger.info("Loaded %d points from cache", count)

        # Populate type filter with grouped categories (preserve bwiki order)
        grouped = {}
        for mt in cache.get("mark_types", []):
            t = mt.get("type", "")
            n = mt.get("mark_type_name", "")
            if not t or not n:
                continue
            if t not in grouped:
                grouped[t] = []
            if n not in grouped[t]:
                grouped[t].append(n)
        point_counts = self._resource_manager.get_point_counts_by_mark_type_name()
        self._sidebar.set_type_filter_items_grouped(grouped, point_counts)

    def _update_data_info(self):
        """更新数据状态显示"""
        # Try auto-load map on startup
        self._try_load_map()

        # Try load points from cache
        cache = self._wiki_updater.get_cached_data()
        if cache and cache.get("points"):
            self._load_points_from_cache()
        elif self._resource_manager.count > 0:
            self._sidebar.set_data_info(f"已加载 {self._resource_manager.count} 个资源")
        else:
            last = self._wiki_updater.get_last_update_time()
            if last:
                self._sidebar.set_data_info(f"上次更新: {last[:10]}")
            else:
                self._sidebar.set_data_info("暂无数据 - 点击更新")

    # ==================== Overlay ====================

    def _on_toggle_overlay(self, enabled: bool):
        if enabled:
            self._overlay_hud.show()
        else:
            self._overlay_hud.set_passthrough_locked(False)
            self._overlay_hud.hide()
        self._sidebar.set_overlay_enabled(enabled)
        self._settings.set("ui.overlay_enabled", enabled)

    def _on_overlay_closed(self):
        self._sidebar.set_overlay_enabled(False)
        self._settings.set("ui.overlay_enabled", False)

    def _on_toggle_overlay_passthrough(self, enabled: bool):
        if not self._settings.get("ui.overlay_enabled", True) or not self._overlay_hud.isVisible():
            self._sidebar.set_overlay_enabled(False)
            return
        self._overlay_hud.set_passthrough_locked(enabled)

    def _on_hud_crop_size_changed(self, size: int):
        self._settings.set("ui.hud_crop_size", size)

    def _on_hud_size_changed(self, w: int, h: int):
        self._settings.set("ui.overlay_size", {"width": w, "height": h})

    def _on_hud_shape_changed(self, shape: str):
        self._settings.set("ui.hud_shape", shape)

    def _apply_display_options(self):
        show_route = self._settings.get("ui.show_route_line", True)
        show_distance = self._settings.get("ui.show_distance", True)
        show_compass = self._settings.get("ui.show_compass", True)
        self._map_canvas.set_show_route_line(show_route)
        self._overlay_hud.set_display_options(
            show_route_line=show_route,
            show_distance=show_distance,
            show_compass=show_compass,
        )

    # ==================== Map click ====================

    def _on_map_clicked(self, x: float, y: float):
        """地图右键点击"""
        logger.debug("Map clicked: (%.0f, %.0f)", x, y)

    def _on_select_region_for_route(self):
        """Enter region selection mode on map canvas."""
        self._map_canvas.start_region_selection()
        self._sidebar.set_data_info("请在地图上框选区域...")

    def _on_region_selected(self, x1, y1, x2, y2):
        """Region selected on map — plan route for points within."""
        selected_names = self._sidebar._get_selected_mark_type_names()
        if selected_names:
            all_resources = self._resource_manager.to_display_list(mark_type_names=selected_names)
        else:
            all_resources = self._resource_manager.to_display_list()

        # Filter to points within the region
        region_resources = [
            r for r in all_resources
            if x1 <= r["x"] <= x2 and y1 <= r["y"] <= y2
        ]

        if not region_resources:
            QMessageBox.information(self, "提示", "选中区域内没有资源点。")
            self._map_canvas.clear_selected_region()
            return

        # 防重入
        if (getattr(self, "_route_worker", None) is not None
                and self._route_worker.isRunning()):
            logger.info("Region plan ignored: previous worker still running")
            return

        self._sidebar.set_data_info(f"区域内 {len(region_resources)} 个点位，正在规划...")
        self._sidebar.set_nav_progress(0, "正在规划路线...")

        start, region_resources = self._route_start_and_targets(
            self._tracker.position, region_resources)
        if not region_resources:
            QMessageBox.information(self, "提示", "选中区域内没有可导航的目标点。")
            self._map_canvas.clear_selected_region()
            self._sidebar.set_nav_progress(0, "规划取消")
            return

        max_points = self._settings.get("navigation.max_route_points", 500)
        if len(region_resources) > max_points:
            QMessageBox.information(self, "提示",
                                    f"选中区域有 {len(region_resources)} 个目标点，超过上限 {max_points}。\n"
                                    "请缩小框选范围，或在设置→性能中调整上限。")
            self._map_canvas.clear_selected_region()
            return
        hubs, end, teleport_cost = self._build_route_kwargs(start)
        self._route_worker = RouteWorker(
            self._path_planner, start, region_resources,
            self._settings.get("navigation.route_strategy", "auto"),
            teleport_hubs=hubs, end=end, teleport_cost=teleport_cost
        )
        self._route_worker.finished.connect(self._on_route_planned)
        self._route_worker.failed.connect(self._on_route_plan_failed)
        self._route_worker.start()

    # ==================== Settings ====================

    def _on_settings(self):
        """打开设置对话框"""
        from .dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self._settings, self)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.exec_()

    # ---- Dependency install (persistent across dialog open/close) ----

    def start_dep_install(self, packages: list, extra_args: list = None,
                          needs_restart: bool = False):
        """Start pip install process (called by SettingsDialog)."""
        if self._dep_install_running:
            return
        self._dep_install_running = True
        self._dep_needs_restart = needs_restart
        self._dep_install_log = ""

        python_exe = sys.executable
        self._dep_install_process = QProcess(self)
        self._dep_install_process.setProcessChannelMode(QProcess.MergedChannels)
        self._dep_install_process.readyReadStandardOutput.connect(
            self._on_dep_install_output
        )
        self._dep_install_process.finished.connect(self._on_dep_install_finished)

        args = ["-m", "pip", "install"] + packages
        if extra_args:
            args.extend(extra_args)

        cmd_text = f"$ {python_exe} -m pip install {' '.join(packages)}\n"
        self._dep_install_log += cmd_text
        self._dep_install_process.start(python_exe, args)
        logger.info("Dep install started: %s", packages)

    def start_dep_uninstall_then_install(self, uninstall_pkgs: list,
                                          install_pkgs: list,
                                          extra_args: list = None):
        """Uninstall packages first, then install new ones."""
        if self._dep_install_running:
            return
        self._dep_install_running = True
        self._dep_needs_restart = True
        self._dep_install_log = ""
        self._pending_install_pkgs = install_pkgs
        self._pending_install_args = extra_args or []

        # Track OpenCV switch for UI display
        if any("opencv-python-cuda-wheels" in pkg or "opencv_contrib_python" in pkg for pkg in install_pkgs):
            self._dep_opencv_switched = "cuda"
        elif "opencv-python" in install_pkgs:
            self._dep_opencv_switched = "cpu"

        python_exe = sys.executable
        self._dep_install_process = QProcess(self)
        self._dep_install_process.setProcessChannelMode(QProcess.MergedChannels)
        self._dep_install_process.readyReadStandardOutput.connect(
            self._on_dep_install_output
        )
        self._dep_install_process.finished.connect(
            self._on_dep_uninstall_finished
        )

        args = ["-m", "pip", "uninstall"] + uninstall_pkgs + ["-y"]
        cmd_text = f"$ pip uninstall {' '.join(uninstall_pkgs)} -y\n"
        self._dep_install_log += cmd_text
        self._dep_install_process.start(python_exe, args)

    def _on_dep_install_output(self):
        data = self._dep_install_process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        self._dep_install_log += text

    def _on_dep_install_finished(self, exit_code, _exit_status):
        self._dep_install_running = False
        if exit_code == 0:
            if self._dep_needs_restart:
                self._dep_install_log += "\n✓ 安装完成，请重启程序。\n"
            else:
                self._dep_install_log += "\n✓ 安装完成。\n"
        else:
            self._dep_install_log += f"\n✗ 安装失败 (exit code {exit_code})。\n"
        logger.info("Dep install finished: exit_code=%d", exit_code)

    def _on_dep_uninstall_finished(self, exit_code, _exit_status):
        self._dep_install_log += f"\n卸载完成 (exit code {exit_code})。\n"
        # Now install
        pkgs = getattr(self, '_pending_install_pkgs', [])
        extra = getattr(self, '_pending_install_args', [])
        if pkgs:
            python_exe = sys.executable
            self._dep_install_process = QProcess(self)
            self._dep_install_process.setProcessChannelMode(QProcess.MergedChannels)
            self._dep_install_process.readyReadStandardOutput.connect(
                self._on_dep_install_output
            )
            self._dep_install_process.finished.connect(
                self._on_dep_install_finished
            )
            args = ["-m", "pip", "install"] + pkgs
            if extra:
                args.extend(extra)
            cmd_text = f"$ pip install {' '.join(pkgs)}\n"
            self._dep_install_log += cmd_text
            self._dep_install_process.start(python_exe, args)
        else:
            self._dep_install_running = False

    def _apply_settings(self):
        """应用设置变更到运行中的模块"""
        # Update tracker config
        interval = self._settings.get("tracking.update_interval", 100)
        if self._tracking_timer.isActive():
            self._tracking_timer.setInterval(interval)
        
        # Update HUD opacity
        opacity = self._settings.get("ui.overlay_opacity", 0.85)
        self._overlay_hud.set_opacity(opacity)
        self._apply_display_options()
        
        # Update navigator
        self._navigator._arrival_distance = self._settings.get("navigation.arrival_distance", 20)
        
        # GPU status display
        self._update_gpu_status()

        # Detection mode
        detection_mode = self._settings.get("tracking.detection_mode", "sift")
        self._minimap_detector.set_detection_mode(detection_mode)

        logger.info("Settings applied")

    # ==================== Misc ====================

    def _update_gpu_status(self):
        # LoFTR (PyTorch CUDA)
        mode = self._settings.get("tracking.detection_mode", "sift")
        if mode in ("ai", "hybrid") and self._minimap_detector.is_ai_available:
            try:
                import torch
                if torch.cuda.is_available():
                    self._status_bar.set_gpu_status("GPU 模式 (LoFTR)")
                    return
            except ImportError:
                pass

        # OpenCV CUDA
        try:
            import cv2
            if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self._status_bar.set_gpu_status("GPU 模式 (CUDA)")
                return
        except Exception:
            pass

        self._status_bar.set_gpu_status("CPU 模式")

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                (geo.width() - self.width()) // 2 + geo.x(),
                (geo.height() - self.height()) // 2 + geo.y()
            )

    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        self._tracking_timer.stop()
        if self._tracker.is_running:
            self._tracker.stop()
        self._navigator.stop()
        self._stop_background_tasks()
        self._overlay_hud.close()
        self._screen_capture.release()
        self._settings.save()
        logger.info("Main window closed, resources released")
        super().closeEvent(event)

    def _stop_background_tasks(self):
        for attr in ("_wiki_worker", "_route_worker"):
            worker = getattr(self, attr, None)
            if worker is not None and worker.isRunning():
                logger.info("Waiting for %s to stop", attr)
                worker.requestInterruption()
                if not worker.wait(3000):
                    logger.warning("%s did not stop in time; terminating", attr)
                    worker.terminate()
                    worker.wait(1000)

        process = getattr(self, "_dep_install_process", None)
        if process is not None and process.state() != QProcess.NotRunning:
            logger.info("Stopping dependency install process")
            process.terminate()
            if not process.waitForFinished(3000):
                process.kill()
                process.waitForFinished(1000)
            self._dep_install_running = False

    # ==================== Properties ====================

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

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        zoom = getattr(self._map_canvas, '_zoom', 1.0)
        self._status_bar.set_zoom(zoom)
