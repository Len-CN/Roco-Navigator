"""
主窗口

组装标题栏、侧边栏、地图画布等组件。
集成追踪、导航、HUD、数据更新等所有核心模块。
无边框窗口 + 新拟物派设计风格。
"""

import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox, QGraphicsDropShadowEffect,
    QApplication, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QResizeEvent

from roco_navigator.config.settings import Settings
from roco_navigator.ui.widgets.title_bar import TitleBar
from roco_navigator.ui.widgets.sidebar import Sidebar
from roco_navigator.ui.map_canvas import MapCanvas
from roco_navigator.ui.overlay_hud import OverlayHUD
from roco_navigator.ui.widgets.neumorphic import (
    BG_PRIMARY, BG_SECONDARY, TEXT_SECONDARY
)
from roco_navigator.utils.gpu_utils import GPUManager

# Core modules
from roco_navigator.core.screen_capture import ScreenCapture
from roco_navigator.core.minimap_detector import MinimapDetector
from roco_navigator.core.position_tracker import PositionTracker, TrackingState, TrackingConfig
from roco_navigator.core.pathfinding import PathPlanner, total_distance
from roco_navigator.core.navigation import Navigator, NavigationState

# Data modules
from roco_navigator.data.map_manager import MapManager
from roco_navigator.data.resource_manager import ResourceManager
from roco_navigator.data.route_manager import RouteManager, Route
from roco_navigator.data.wiki_updater import WikiUpdater

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
            success, msg = self._updater.download_map(zoom=6, progress_callback=cb)
        else:
            success, msg = self._updater.update_points(progress_callback=cb)
        self.finished.emit(success, msg)


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

        self._gpu_label = QLabel("CPU Mode")
        self._gpu_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._gpu_label)

        layout.addStretch()

        self._fps_label = QLabel("-- FPS")
        self._fps_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._fps_label)

        self._state_label = QLabel("Idle")
        self._state_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._state_label)

        self._pos_label = QLabel("Position: --")
        self._pos_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._pos_label)

        self._zoom_label = QLabel("Zoom: 100%")
        self._zoom_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        layout.addWidget(self._zoom_label)

    def set_gpu_status(self, text: str):
        self._gpu_label.setText(text)

    def set_fps(self, fps: float):
        self._fps_label.setText(f"{fps:.0f} FPS")

    def set_state(self, text: str):
        self._state_label.setText(text)

    def set_position(self, x: float, y: float):
        self._pos_label.setText(f"Pos: ({x:.0f}, {y:.0f})")

    def set_zoom(self, zoom: float):
        self._zoom_label.setText(f"Zoom: {zoom * 100:.0f}%")

    def clear_position(self):
        self._pos_label.setText("Position: --")


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
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1200, 800)
        self.setWindowTitle("Roco Navigator")
        self.setStyleSheet(f"QMainWindow {{ background-color: {BG_PRIMARY}; }}")

        # ---- 初始化核心模块 ----
        self._screen_capture = ScreenCapture()
        self._map_manager = MapManager()
        self._resource_manager = ResourceManager()
        self._route_manager = RouteManager()
        self._wiki_updater = WikiUpdater()

        use_gpu = settings.get("performance.use_gpu", False)
        self._minimap_detector = MinimapDetector(
            use_clahe=settings.get("minimap_detection.use_clahe", True),
            use_ring_mask=settings.get("minimap_detection.use_ring_mask", True),
            use_gpu=use_gpu,
            sift_ratio=settings.get("minimap_detection.sift_ratio_threshold", 0.7),
            min_matches=settings.get("minimap_detection.min_good_matches", 10),
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

        # ---- 构建 UI ----
        self._setup_ui()

        # ---- 悬浮窗 HUD ----
        self._overlay_hud = OverlayHUD(size="medium")
        if settings.get("ui.overlay_enabled", True):
            self._overlay_hud.show()
        self._overlay_hud.closed.connect(
            lambda: self._sidebar._overlay_check.setChecked(False)
        )

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
        self._center_on_screen()

        logger.info("Main window initialized with all modules integrated")

    def _setup_ui(self):
        """构建 UI 布局"""
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG_PRIMARY}; border-radius: 16px;")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏
        self._title_bar = TitleBar(self, title="Roco Navigator")
        main_layout.addWidget(self._title_bar)

        # 内容区域
        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_PRIMARY};")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(12)

        self._sidebar = Sidebar()
        self._connect_sidebar_signals()
        content_layout.addWidget(self._sidebar)

        self._map_canvas = MapCanvas()
        self._map_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._map_canvas.position_clicked.connect(self._on_map_clicked)
        content_layout.addWidget(self._map_canvas, stretch=1)

        main_layout.addWidget(content, stretch=1)

        self._status_bar = StatusBarWidget()
        main_layout.addWidget(self._status_bar)

    def _connect_sidebar_signals(self):
        self._sidebar.calibrate_clicked.connect(self._on_calibrate)
        self._sidebar.start_tracking_clicked.connect(self._on_start_tracking)
        self._sidebar.stop_tracking_clicked.connect(self._on_stop_tracking)
        self._sidebar.plan_route_clicked.connect(self._on_plan_route)
        self._sidebar.start_nav_clicked.connect(self._on_start_nav)
        self._sidebar.stop_nav_clicked.connect(self._on_stop_nav)
        self._sidebar.update_points_clicked.connect(self._on_update_points)
        self._sidebar.update_map_clicked.connect(self._on_update_map)
        self._sidebar.toggle_overlay_clicked.connect(self._on_toggle_overlay)
        self._sidebar.settings_clicked.connect(self._on_settings)

    # ==================== Tracking ====================

    def _on_calibrate(self):
        """打开小地图校准选择器"""
        logger.info("Calibrate minimap requested")
        from roco_navigator.ui.widgets.minimap_selector import MinimapSelector

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
            QMessageBox.warning(self, "Warning",
                                "Please calibrate the minimap first.\n"
                                "Click 'Calibrate Minimap' to select the minimap area.")
            self._sidebar.set_tracking_active(False)
            return

        if not self._map_manager.is_loaded:
            QMessageBox.warning(self, "Warning",
                                "No map loaded. Please load a map image first.\n"
                                "Place map files in assets/maps/ directory.")
            self._sidebar.set_tracking_active(False)
            return

        self._tracker.set_minimap_region(region)
        self._tracker.start()

        interval = self._settings.get("tracking.update_interval", 100)
        self._tracking_timer.start(interval)

        self._title_bar.set_status("tracking")
        self._title_bar.set_status_text("Tracking")
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
            TrackingState.IDLE: ("idle", "Idle"),
            TrackingState.GLOBAL_SCAN: ("tracking", "Scanning..."),
            TrackingState.PRECISE_TRACK: ("active", "Tracking"),
            TrackingState.INERTIA_NAV: ("warning", "Inertia"),
            TrackingState.LOST: ("error", "Lost"),
        }
        status, text = state_map.get(state, ("idle", ""))
        self._title_bar.set_status(status)
        self._title_bar.set_status_text(text)
        self._sidebar.set_tracking_status(status, text)

    # ==================== Navigation ====================

    def _on_plan_route(self):
        """规划路线"""
        resources = self._resource_manager.to_display_list()
        if not resources:
            QMessageBox.information(self, "Info",
                                    "No resources loaded.\n"
                                    "Update from WIKI or add resources manually.")
            return

        targets = [(r["x"], r["y"]) for r in resources]
        names = [r["name"] for r in resources]
        start = self._tracker.position or (0, 0)

        strategy = self._settings.get("navigation.route_strategy", "nearest")
        route = self._path_planner.plan_route(start, targets, strategy)
        dist = total_distance(route)

        # 保存路线
        route_obj = Route(
            id=f"auto_{len(self._route_manager.get_all()) + 1}",
            name=f"Auto Route ({len(route) - 1} pts)",
            targets=route[1:],
            total_distance=dist,
            strategy=strategy,
        )
        self._route_manager.add(route_obj)

        # 显示在地图上
        self._map_canvas.set_route([(p[0], p[1]) for p in route])

        self._sidebar.set_nav_progress(0, f"Route: {len(route)-1} targets, {dist:.0f}px")
        logger.info("Route planned: %d targets, %.0f total distance", len(route) - 1, dist)

    def _on_start_nav(self):
        """开始导航"""
        if not self._map_canvas._route_points:
            QMessageBox.information(self, "Info", "No route planned. Plan a route first.")
            self._sidebar.set_nav_active(False)
            return

        route = [(p.x(), p.y()) for p in self._map_canvas._route_points]
        self._navigator.start(route)

        self._title_bar.set_status("active")
        self._title_bar.set_status_text("Navigating")
        logger.info("Navigation started")

    def _on_stop_nav(self):
        """停止导航"""
        self._navigator.stop()
        self._title_bar.set_status("tracking" if self._tracker.is_running else "idle")
        self._title_bar.set_status_text("Tracking" if self._tracker.is_running else "")
        self._sidebar.set_nav_progress(0, "Navigation stopped")
        logger.info("Navigation stopped")

    def _on_target_reached(self, index: int, target):
        logger.info("Target %d reached: (%.0f, %.0f)", index, target[0], target[1])
        self._map_canvas.set_route(
            [(p.x(), p.y()) for p in self._map_canvas._route_points],
            current_index=index + 1
        )

    def _on_navigation_complete(self):
        logger.info("Navigation complete!")
        self._sidebar.set_nav_active(False)
        self._sidebar.set_nav_progress(100, "Navigation complete!")
        self._title_bar.set_status("active")
        self._title_bar.set_status_text("Complete")

    def _update_hud_from_nav(self, tracking_status, nav_info):
        """更新 HUD 显示"""
        if not self._overlay_hud.isVisible():
            return

        pos = tracking_status.position
        if pos is None:
            return

        # 获取地图裁剪
        crop, rel = self._map_manager.get_map_crop_centered(pos[0], pos[1], 600)
        if crop is None:
            return

        # 转换路线点为裁剪图相对坐标
        route_rel = []
        half = 300  # crop_size / 2
        for pt in self._navigator.route:
            rx = pt[0] - pos[0] + half
            ry = pt[1] - pos[1] + half
            route_rel.append((rx, ry))

        target_rel = None
        if nav_info.current_target:
            target_rel = (
                nav_info.current_target[0] - pos[0] + half,
                nav_info.current_target[1] - pos[1] + half,
            )

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
        )

    # ==================== Data ====================

    def _on_update_points(self):
        """WIKI 点位数据更新"""
        if self._wiki_updater.is_updating:
            QMessageBox.information(self, "Info", "Update already in progress.")
            return

        self._sidebar.set_data_info("Updating points...")
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
            self._sidebar.set_data_info(f"Failed: {message}")
            logger.error("Points update failed: %s", message)

    def _on_update_map(self):
        """WIKI 地图下载"""
        if self._wiki_updater.is_updating:
            QMessageBox.information(self, "Info", "Update already in progress.")
            return

        self._sidebar.set_data_info("Downloading map...")
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
            self._sidebar.set_data_info(f"Failed: {message}")
            logger.error("Map update failed: %s", message)

    def _try_load_map(self):
        """尝试加载已下载的地图"""
        # Try zoom levels from high to low
        for z in [6, 7, 5, 8, 4]:
            map_path = self._wiki_updater.get_map_path(z)
            if map_path:
                if self._map_manager.load_map(map_path, f"world_z{z}"):
                    self._map_canvas.load_map_image(map_path)
                    self._sidebar.set_data_info(
                        f"Map loaded: {self._map_manager.map_width}x{self._map_manager.map_height}"
                    )
                    logger.info("Map auto-loaded: %s", map_path)
                    return True
        return False

    def _load_points_from_cache(self):
        """从缓存加载点位数据到 ResourceManager"""
        cache = self._wiki_updater.get_cached_data()
        if not cache:
            return

        from roco_navigator.data.resource_manager import Resource

        points = cache.get("points", [])
        mark_type_map = {}
        for mt in cache.get("mark_types", []):
            mark_type_map[mt.get("mark_type", 0)] = mt

        self._resource_manager.clear()
        for pt in points:
            mt_id = pt.get("mark_type", 0)
            mt_info = mark_type_map.get(mt_id, {})
            self._resource_manager.add(Resource(
                id=pt.get("id", ""),
                name=pt.get("name", mt_info.get("mark_type_name", "")),
                type=mt_info.get("type", ""),
                x=pt.get("x", 0),
                y=pt.get("y", 0),
                mark_type=mt_id,
                icon_url=mt_info.get("icon_url", ""),
                description=pt.get("desc", ""),
                source="wiki",
            ))

        count = self._resource_manager.count
        self._map_canvas.set_resources(self._resource_manager.to_display_list())
        self._sidebar.set_data_info(f"{count} points loaded from WIKI")
        logger.info("Loaded %d points from cache", count)

    def _update_data_info(self):
        """更新数据状态显示"""
        # Try auto-load map on startup
        self._try_load_map()

        # Try load points from cache
        cache = self._wiki_updater.get_cached_data()
        if cache and cache.get("points"):
            self._load_points_from_cache()
        elif self._resource_manager.count > 0:
            self._sidebar.set_data_info(f"{self._resource_manager.count} resources loaded")
        else:
            last = self._wiki_updater.get_last_update_time()
            if last:
                self._sidebar.set_data_info(f"Last update: {last[:10]}")
            else:
                self._sidebar.set_data_info("No data - click Update")

    # ==================== Overlay ====================

    def _on_toggle_overlay(self, enabled: bool):
        if enabled:
            self._overlay_hud.show()
        else:
            self._overlay_hud.hide()
        self._settings.set("ui.overlay_enabled", enabled)

    # ==================== Map click ====================

    def _on_map_clicked(self, x: float, y: float):
        """地图右键点击"""
        logger.debug("Map clicked: (%.0f, %.0f)", x, y)

    # ==================== Settings ====================

    def _on_settings(self):
        logger.info("Settings requested")
        # Settings dialog would go here in a future stage

    # ==================== Misc ====================

    def _update_gpu_status(self):
        gpu = GPUManager()
        if gpu.check_gpu_available():
            if self._settings.get("performance.use_gpu", False):
                self._status_bar.set_gpu_status("GPU Mode (CUDA)")
            else:
                self._status_bar.set_gpu_status("GPU Available (Disabled)")
        else:
            self._status_bar.set_gpu_status("CPU Mode")

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
        self._overlay_hud.close()
        self._screen_capture.release()
        self._settings.save()
        logger.info("Main window closed, resources released")
        super().closeEvent(event)

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
