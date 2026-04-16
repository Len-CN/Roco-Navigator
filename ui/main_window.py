"""
主窗口

组装标题栏、侧边栏、地图画布等组件。
集成追踪、导航、HUD、数据更新等所有核心模块。
无边框窗口 + 新拟物派设计风格。
"""

import logging
import sys
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox,
    QApplication, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QProcess
from PyQt5.QtGui import QColor, QResizeEvent, QPainter, QPainterPath

from roco_navigator.config.settings import Settings
from roco_navigator.ui.widgets.title_bar import TitleBar
from roco_navigator.ui.widgets.sidebar import Sidebar
from roco_navigator.ui.map_canvas import MapCanvas
from roco_navigator.ui.overlay_hud import OverlayHUD
from roco_navigator.ui.widgets.neumorphic import (
    BG_PRIMARY, BG_SECONDARY, TEXT_SECONDARY
)
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
            success, msg = self._updater.download_map(zoom=7, progress_callback=cb)
        else:
            success, msg = self._updater.update_points(progress_callback=cb)
        self.finished.emit(success, msg)


class RouteWorker(QThread):
    """路线规划后台线程"""
    finished = pyqtSignal(list, float, list)

    def __init__(self, planner, start_pos, resources, strategy):
        super().__init__()
        self._planner = planner
        self._start = start_pos or (resources[0]["x"], resources[0]["y"])
        self._resources = resources
        self._strategy = strategy

    def run(self):
        from roco_navigator.core.pathfinding import total_distance
        targets = [(r["x"], r["y"]) for r in self._resources]
        names = [r.get("name", "") for r in self._resources]
        route = self._planner.plan_route(self._start, targets, self._strategy)
        dist = total_distance(route)
        self.finished.emit(route, dist, names)


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

        # ---- 构建 UI ----
        self._setup_ui()

        # ---- 悬浮窗 HUD ----
        hud_size = settings.get("ui.overlay_size", {"width": 320, "height": 400})
        hud_shape = settings.get("ui.hud_shape", "rounded_rect")
        self._overlay_hud = OverlayHUD(
            size="medium",
            custom_w=hud_size.get("width", 0),
            custom_h=hud_size.get("height", 0),
            shape=hud_shape,
        )
        if settings.get("ui.overlay_enabled", True):
            self._overlay_hud.show()
        self._overlay_hud.closed.connect(
            lambda: self._sidebar._overlay_check.setChecked(False)
        )
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

        self._sidebar = Sidebar()
        self._connect_sidebar_signals()
        content_layout.addWidget(self._sidebar)

        self._map_canvas = MapCanvas()
        self._map_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._map_canvas.position_clicked.connect(self._on_map_clicked)
        self._map_canvas.region_selected.connect(self._on_region_selected)
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

    def _on_plan_route_for_type(self, selected_names):
        """为选中类型的资源规划路线 - selected_names is a set of mark_type_name strings"""
        if selected_names:
            resources = self._resource_manager.to_display_list(mark_type_names=selected_names)
        else:
            resources = self._resource_manager.to_display_list()

        if not resources:
            QMessageBox.information(self, "提示", "当前筛选条件下没有资源点。")
            return

        if len(resources) > 500:
            QMessageBox.information(self, "提示",
                                    f"当前筛选有 {len(resources)} 个点位，数量过多。\n"
                                    "请选择具体的资源类型进行规划。")
            return

        self._sidebar.set_nav_progress(0, "正在规划路线...")

        # Run in background
        self._route_worker = RouteWorker(
            self._path_planner, self._tracker.position, resources,
            self._settings.get("navigation.route_strategy", "nearest")
        )
        self._route_worker.finished.connect(self._on_route_planned)
        self._route_worker.start()

    def _on_route_planned(self, route, dist, names):
        """路线规划完成回调"""
        if not route or len(route) < 2:
            self._sidebar.set_nav_progress(0, "规划失败")
            return

        selected = self._sidebar._get_selected_mark_type_names()
        type_name = ", ".join(sorted(selected)) if selected else "全部"
        route_obj = Route(
            id=f"auto_{len(self._route_manager.get_all()) + 1}",
            name=f"{type_name} ({len(route) - 1} 个点)",
            targets=route[1:],
            total_distance=dist,
            strategy="nearest",
        )
        self._route_manager.add(route_obj)
        self._map_canvas.set_route([(p[0], p[1]) for p in route])
        self._map_canvas.clear_selected_region()
        self._sidebar.set_nav_progress(0, f"路线: {len(route)-1} 个目标, {dist:.0f}px")
        logger.info("Route planned: %d targets, %.0f distance", len(route) - 1, dist)

    def _on_start_nav(self):
        """开始导航"""
        if not self._map_canvas._route_points:
            QMessageBox.information(self, "提示", "暂无规划路线。请先规划路线。")
            self._sidebar.set_nav_active(False)
            return

        route = [(p.x(), p.y()) for p in self._map_canvas._route_points]
        self._navigator.start(route)

        self._title_bar.set_status("active")
        self._title_bar.set_status_text("导航中")
        logger.info("Navigation started")

    def _on_stop_nav(self):
        """停止导航"""
        self._navigator.stop()
        self._title_bar.set_status("tracking" if self._tracker.is_running else "idle")
        self._title_bar.set_status_text("追踪中" if self._tracker.is_running else "")
        self._sidebar.set_nav_progress(0, "导航已停止")
        logger.info("Navigation stopped")

    def _on_target_reached(self, index: int, target):
        logger.info("Target %d reached: (%.0f, %.0f)", index, target[0], target[1])
        self._map_canvas.set_route(
            [(p.x(), p.y()) for p in self._map_canvas._route_points],
            current_index=index + 1,
            visited=self._navigator.visited_indices
        )

    def _on_navigation_complete(self):
        logger.info("Navigation complete!")
        self._sidebar.set_nav_active(False)
        self._sidebar.set_nav_progress(100, "导航完成！")
        self._title_bar.set_status("active")
        self._title_bar.set_status_text("已完成")

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
        half = hud_crop_size / 2
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

        # Gather resource points within the crop area
        resource_rel = []
        crop_x1 = pos[0] - half
        crop_y1 = pos[1] - half
        display_list = self._resource_manager.to_display_list()
        for res in display_list:
            rx = res["x"] - crop_x1
            ry = res["y"] - crop_y1
            # Only include points within crop bounds (with small margin)
            if -10 <= rx <= hud_crop_size + 10 and -10 <= ry <= hud_crop_size + 10:
                resource_rel.append({
                    "rx": rx, "ry": ry,
                    "type": res.get("type", ""),
                    "name": res.get("name", ""),
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

        from roco_navigator.data.resource_manager import Resource

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
            self._overlay_hud.hide()
        self._settings.set("ui.overlay_enabled", enabled)

    def _on_toggle_overlay_passthrough(self, enabled: bool):
        self._overlay_hud.set_passthrough_locked(enabled)

    def _on_hud_crop_size_changed(self, size: int):
        self._settings.set("ui.hud_crop_size", size)

    def _on_hud_size_changed(self, w: int, h: int):
        self._settings.set("ui.overlay_size", {"width": w, "height": h})

    def _on_hud_shape_changed(self, shape: str):
        self._settings.set("ui.hud_shape", shape)

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
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "选中区域内没有资源点。")
            self._map_canvas.clear_selected_region()
            return

        self._sidebar.set_data_info(f"区域内 {len(region_resources)} 个点位，正在规划...")
        self._sidebar.set_nav_progress(0, "正在规划路线...")

        self._route_worker = RouteWorker(
            self._path_planner, self._tracker.position, region_resources,
            self._settings.get("navigation.route_strategy", "auto")
        )
        self._route_worker.finished.connect(self._on_route_planned)
        self._route_worker.start()

    # ==================== Settings ====================

    def _on_settings(self):
        """打开设置对话框"""
        from roco_navigator.ui.dialogs.settings_dialog import SettingsDialog
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
