"""
位置追踪器

实现三阶段追踪策略:
1. GLOBAL_SCAN - 全局扫描，在整个地图中搜索玩家位置
2. PRECISE_TRACK - 精确追踪，在上次位置附近小范围搜索
3. INERTIA_NAV - 惯性导航，使用运动预测维持定位

基于 Game-Map-Tracker 的状态机设计。
"""

import logging
import math
import time
from typing import Optional, Tuple, Callable
from enum import Enum
from dataclasses import dataclass
from collections import deque

from .screen_capture import ScreenCapture
from .minimap_detector import MinimapDetector, DetectionResult
from ..data.map_manager import MapManager

logger = logging.getLogger(__name__)


class TrackingState(Enum):
    """追踪状态"""
    IDLE = "idle"                     # 未启动
    GLOBAL_SCAN = "global_scan"       # 全局扫描
    PRECISE_TRACK = "precise_track"   # 精确追踪
    INERTIA_NAV = "inertia_nav"       # 惯性导航
    LOST = "lost"                     # 完全丢失


@dataclass
class TrackingConfig:
    """追踪配置"""
    global_scan_step: int = 1400       # 全局扫描步长 (像素)
    global_scan_size: int = 1600       # 全局扫描窗口大小
    tracking_radius: int = 300         # 精确追踪搜索半径 (zoom 7 下 300px 足够覆盖帧间移动)
    max_lost_frames: int = 30          # 最大丢失帧数 -> 惯性导航
    max_inertia_frames: int = 100      # 最大惯性帧数 -> 重新全局扫描
    teleport_threshold: float = 200.0  # 传送检测阈值
    update_interval_ms: int = 100      # 更新间隔 (毫秒)


@dataclass
class TrackingStatus:
    """追踪状态信息"""
    state: TrackingState
    position: Optional[Tuple[float, float]]
    direction: float
    confidence: float
    fps: float
    lost_frames: int
    detail: str


class PositionTracker:
    """
    位置追踪器

    三阶段追踪:
    - GLOBAL_SCAN: 启动时或完全丢失后，滑动窗口遍历整个地图
    - PRECISE_TRACK: 找到位置后，在上次位置附近小范围搜索
    - INERTIA_NAV: 连续丢失时，使用运动预测

    合规声明:
    - 仅读取屏幕像素，不注入任何游戏进程
    - 不模拟任何键盘/鼠标操作
    """

    def __init__(self,
                 screen_capture: ScreenCapture,
                 minimap_detector: MinimapDetector,
                 map_manager: MapManager,
                 config: Optional[TrackingConfig] = None):
        self._capture = screen_capture
        self._detector = minimap_detector
        self._map_manager = map_manager
        self._config = config or TrackingConfig()

        # 状态
        self._state = TrackingState.IDLE
        self._running = False
        self._position: Optional[Tuple[float, float]] = None
        self._prev_position: Optional[Tuple[float, float]] = None
        self._direction: float = 0.0
        self._confidence: float = 0.0
        self._lost_frames: int = 0

        # EMA 位置平滑
        self._smoothed_x: Optional[float] = None
        self._smoothed_y: Optional[float] = None

        # 小地图区域配置
        self._minimap_region: Optional[dict] = None  # {"x", "y", "width", "height"}

        # 性能计数
        self._frame_count: int = 0
        self._last_time: float = 0.0
        self._fps: float = 0.0
        self._dt_history: deque = deque(maxlen=10)  # FPS 滑动窗口

        # 箭头检测降频 (每 2 帧检测一次，方向检测已优化)
        self._arrow_detect_interval: int = 2

        # 性能优化: 高置信度帧跳过
        self._skip_counter: int = 0        # 连续跳过帧计数
        self._max_skip: int = 1            # 最大连续跳过帧数
        self._skip_confidence_threshold: float = 0.7  # 跳过所需最低置信度
        self._skip_dist_threshold: float = 5.0        # 上帧位移 < 此值才跳过

        # 全局扫描分帧状态
        self._scan_positions: list = []
        self._scan_idx: int = 0

        # 回调
        self._on_position_update: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None

        logger.info("PositionTracker initialized")

    # ==================== 配置 ====================

    def set_minimap_region(self, region: dict):
        """设置小地图截图区域"""
        self._minimap_region = region
        logger.info("Minimap region set: %s", region)

    def set_on_position_update(self, callback: Callable):
        """设置位置更新回调"""
        self._on_position_update = callback

    def set_on_state_change(self, callback: Callable):
        """设置状态变化回调"""
        self._on_state_change = callback

    # ==================== 控制 ====================

    def start(self):
        """开始追踪"""
        if self._minimap_region is None:
            logger.error("Minimap region not set, cannot start tracking")
            return

        if not self._map_manager.is_loaded:
            logger.error("Map not loaded, cannot start tracking")
            return

        self._running = True
        self._lost_frames = 0
        self._prev_position = None
        self._change_state(TrackingState.GLOBAL_SCAN)
        self._last_time = time.perf_counter()
        logger.info("Tracking started")

    def stop(self):
        """停止追踪"""
        self._running = False
        self._smoothed_x = None
        self._smoothed_y = None
        self._scan_positions = []
        self._change_state(TrackingState.IDLE)
        logger.info("Tracking stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ==================== EMA 位置平滑 ====================

    def _smooth_position(self, raw_x: float, raw_y: float) -> Tuple[float, float]:
        """
        自适应 EMA 位置平滑（参考 Game-Map-Tracker）

        - 首次定位：直接赋值，不平滑
        - dist > 500px：跳变/传送，直接接受不平滑
        - dist < 15px：alpha=0.15（慢平滑，减少抖动）
        - dist >= 15px：alpha=0.45（快跟随，跟上移动）

        Args:
            raw_x: 原始 X 坐标
            raw_y: 原始 Y 坐标

        Returns:
            平滑后的 (x, y) 坐标
        """
        if self._smoothed_x is None or self._smoothed_y is None:
            # 首次定位，直接赋值
            self._smoothed_x = raw_x
            self._smoothed_y = raw_y
            return (raw_x, raw_y)

        dx = raw_x - self._smoothed_x
        dy = raw_y - self._smoothed_y
        dist = (dx * dx + dy * dy) ** 0.5

        if dist > 500:
            # 跳变/传送，直接接受不平滑
            self._smoothed_x = raw_x
            self._smoothed_y = raw_y
            return (raw_x, raw_y)

        if dist < 15:
            alpha = 0.15  # 慢平滑，减少抖动
        else:
            alpha = 0.45  # 快跟随，跟上移动

        self._smoothed_x = alpha * raw_x + (1 - alpha) * self._smoothed_x
        self._smoothed_y = alpha * raw_y + (1 - alpha) * self._smoothed_y

        return (self._smoothed_x, self._smoothed_y)

    # ==================== 核心追踪循环 ====================

    def update(self) -> Optional[TrackingStatus]:
        """
        执行一帧追踪更新

        由主循环定时调用（或在独立线程中运行）。

        Returns:
            TrackingStatus 或 None
        """
        if not self._running:
            return None

        # 性能计时 (滑动窗口平均 FPS)
        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now
        self._frame_count += 1
        if dt > 0:
            self._dt_history.append(dt)
            avg_dt = sum(self._dt_history) / len(self._dt_history)
            self._fps = 1.0 / avg_dt if avg_dt > 0 else 0.0

        # 截取小地图
        minimap = self._capture_minimap()
        if minimap is None:
            return self._build_status("Failed to capture minimap")

        # 根据状态执行不同策略 (传递原始 BGR 用于箭头检测)
        if self._state == TrackingState.GLOBAL_SCAN:
            return self._do_global_scan(minimap)
        elif self._state == TrackingState.PRECISE_TRACK:
            return self._do_precise_track(minimap)
        elif self._state == TrackingState.INERTIA_NAV:
            return self._do_inertia_nav(minimap)
        else:
            return self._build_status("Unknown state")

    def _do_global_scan(self, minimap) -> TrackingStatus:
        """
        全局扫描: 预计算模式下单次全局匹配，否则分帧滑动窗口（不阻塞 UI）
        """
        # 预计算模式: 单次全局匹配 (O(1) 帧耗时，不需要滑动窗口)
        if self._detector._sift_matcher.is_precomputed:
            minimap_gray = self._detector._image_processor.preprocess_minimap(
                minimap, self._detector._use_clahe, self._detector._use_ring_mask,
                self._detector._ring_outer, self._detector._ring_inner)
            minimap_mask = None
            if self._detector._use_ring_mask:
                h, w = minimap_gray.shape[:2]
                minimap_mask = self._detector._image_processor.create_ring_mask(
                    min(h, w), self._detector._ring_outer, self._detector._ring_inner)
            result = self._detector._sift_matcher.match_precomputed(
                minimap_gray, search_center=None, minimap_mask=minimap_mask)
            if result.success and result.confidence > 0.15:
                self._position = result.position
                if result.position is not None:
                    self._smoothed_x = result.position[0]
                    self._smoothed_y = result.position[1]
                self._confidence = result.confidence
                self._lost_frames = 0
                self._change_state(TrackingState.PRECISE_TRACK)
                self._notify_position()
                return self._build_status(
                    f"Global scan found: ({result.position[0]:.0f}, {result.position[1]:.0f})"
                )
            # 预计算全局搜索失败 → 下一帧重试，不阻塞 UI
            return self._build_status("Global scan: no match, retrying next frame")

        # 非预计算模式: 分帧滑动窗口 (每帧只扫描一个窗口，不阻塞 UI)
        step = self._config.global_scan_step
        win_size = self._config.global_scan_size
        mw = self._map_manager.map_width
        mh = self._map_manager.map_height

        # 计算所有窗口位置
        if not hasattr(self, '_scan_positions') or not self._scan_positions:
            self._scan_positions = [
                (x, y)
                for y in range(0, mh, step)
                for x in range(0, mw, step)
            ]
            self._scan_idx = 0

        # 每帧只扫描一个窗口
        if self._scan_idx < len(self._scan_positions):
            x, y = self._scan_positions[self._scan_idx]
            self._scan_idx += 1

            region = self._map_manager.get_logic_region(x, y, win_size, win_size, copy=False)
            if region is not None:
                result = self._detector.detect(minimap, region, region_offset=(x, y))

                if result.success and result.confidence > 0.3:
                    self._position = result.position
                    if result.position is not None:
                        self._smoothed_x = result.position[0]
                        self._smoothed_y = result.position[1]
                    self._confidence = result.confidence
                    self._lost_frames = 0
                    self._scan_positions = []
                    self._change_state(TrackingState.PRECISE_TRACK)
                    self._notify_position()
                    return self._build_status(
                        f"Global scan found: ({result.position[0]:.0f}, {result.position[1]:.0f})"
                    )

            progress = self._scan_idx
            total = len(self._scan_positions)
            return self._build_status(f"Global scan: window {progress}/{total}")

        # 所有窗口扫描完毕，重置
        self._scan_positions = []
        return self._build_status("Global scan: no match found, restarting")

    def _do_precise_track(self, minimap) -> TrackingStatus:
        """
        精确追踪: 在上次位置附近小范围搜索
        """
        if self._position is None:
            self._change_state(TrackingState.GLOBAL_SCAN)
            return self._build_status("No position, switching to global scan")

        px, py = self._position
        radius = self._config.tracking_radius

        # 帧跳过: 高置信度+位置稳定时跳过 SIFT，只做箭头检测
        if (self._confidence >= self._skip_confidence_threshold
                and self._skip_counter < self._max_skip
                and self._prev_position is not None):
            dx_skip = px - self._prev_position[0]
            dy_skip = py - self._prev_position[1]
            dist_skip = (dx_skip * dx_skip + dy_skip * dy_skip) ** 0.5
            if dist_skip < self._skip_dist_threshold:
                self._skip_counter += 1
                # 只做箭头检测
                if self._frame_count % self._arrow_detect_interval == 0:
                    arrow_dir = self._detector._arrow_detector.detect_direction(minimap)
                    if arrow_dir is not None:
                        self._direction = arrow_dir
                self._notify_position()
                return self._build_status(
                    f"Tracking (skip): ({px:.0f}, {py:.0f}) conf={self._confidence:.2f}"
                )
        self._skip_counter = 0

        # Use precomputed features with local search if available
        if self._detector._sift_matcher.is_precomputed:
            minimap_gray = self._detector._image_processor.preprocess_minimap(
                minimap, self._detector._use_clahe, self._detector._use_ring_mask,
                self._detector._ring_outer, self._detector._ring_inner)
            minimap_mask = None
            if self._detector._use_ring_mask:
                h, w = minimap_gray.shape[:2]
                minimap_mask = self._detector._image_processor.create_ring_mask(
                    min(h, w), self._detector._ring_outer, self._detector._ring_inner)
            result_sift = self._detector._sift_matcher.match_precomputed(
                minimap_gray,
                search_center=self._position,
                search_radius=radius,
                minimap_mask=minimap_mask)

            if result_sift.success:
                # 传送检测
                if self._position and result_sift.position:
                    dist = ((result_sift.position[0] - self._position[0]) ** 2 +
                            (result_sift.position[1] - self._position[1]) ** 2) ** 0.5
                    if dist > self._config.teleport_threshold:
                        logger.warning("Teleport detected (%.0f px), re-scanning", dist)
                        self._change_state(TrackingState.GLOBAL_SCAN)
                        return self._build_status(f"Teleport detected ({dist:.0f} px)")

                # EMA 平滑后赋值
                if result_sift.position is not None:
                    smoothed = self._smooth_position(result_sift.position[0], result_sift.position[1])
                    self._position = smoothed
                else:
                    self._position = result_sift.position
                self._confidence = result_sift.confidence
                self._lost_frames = 0

                # 箭头方向检测 (每 N 帧一次)
                if self._frame_count % self._arrow_detect_interval == 0:
                    arrow_dir = self._detector._arrow_detector.detect_direction(minimap)
                    if arrow_dir is not None:
                        self._direction = arrow_dir

                # Fallback: compute direction from displacement
                if self._prev_position is not None and result_sift.position is not None:
                    dx = result_sift.position[0] - self._prev_position[0]
                    dy = result_sift.position[1] - self._prev_position[1]
                    dist_moved = (dx * dx + dy * dy) ** 0.5
                    if dist_moved > 3.0 and self._frame_count % self._arrow_detect_interval != 0:
                        self._direction = (math.degrees(math.atan2(dx, -dy))) % 360
                if result_sift.position is not None:
                    self._prev_position = result_sift.position

                self._notify_position()
                return self._build_status(
                    f"Tracking: ({self._position[0]:.0f}, {self._position[1]:.0f}) "
                    f"conf={self._confidence:.2f}"
                )
            else:
                # LoFTR fallback (if SIFT failed and AI is available)
                if self._detector.should_use_ai_fallback:
                    region = self._map_manager.get_logic_region(
                        int(max(0, px - radius)), int(max(0, py - radius)),
                        radius * 2, radius * 2, copy=False
                    )
                    if region is not None:
                        success, ai_result = self._detector.try_ai_match(
                            minimap, region,
                            (int(max(0, px - radius)), int(max(0, py - radius)))
                        )
                        if success:
                            # EMA 平滑后赋值
                            if ai_result.position is not None:
                                smoothed = self._smooth_position(ai_result.position[0], ai_result.position[1])
                                self._position = smoothed
                            else:
                                self._position = ai_result.position
                            self._confidence = ai_result.confidence
                            self._lost_frames = 0
                            # 箭头方向检测
                            if self._frame_count % self._arrow_detect_interval == 0:
                                arrow_dir = self._detector._arrow_detector.detect_direction(minimap)
                                if arrow_dir is not None:
                                    self._direction = arrow_dir
                            if self._prev_position is not None and ai_result.position is not None:
                                dx = ai_result.position[0] - self._prev_position[0]
                                dy = ai_result.position[1] - self._prev_position[1]
                                dist_moved = (dx * dx + dy * dy) ** 0.5
                                if dist_moved > 3.0 and self._frame_count % self._arrow_detect_interval != 0:
                                    self._direction = (math.degrees(math.atan2(dx, -dy))) % 360
                            if ai_result.position is not None:
                                self._prev_position = ai_result.position
                            self._notify_position()
                            return self._build_status(
                                f"Tracking (LoFTR): ({self._position[0]:.0f}, {self._position[1]:.0f}) "
                                f"conf={self._confidence:.2f}"
                            )

                self._lost_frames += 1
                if self._lost_frames > self._config.max_lost_frames:
                    self._change_state(TrackingState.INERTIA_NAV)
                    return self._build_status("Too many lost frames, entering inertia mode")
                return self._build_status(f"Lost frame {self._lost_frames}/{self._config.max_lost_frames}")

        # Fallback: original region-based tracking
        x1 = int(max(0, px - radius))
        y1 = int(max(0, py - radius))
        w = radius * 2
        h = radius * 2

        region = self._map_manager.get_logic_region(x1, y1, w, h, copy=False)
        if region is None:
            self._lost_frames += 1
            return self._build_status("Failed to get search region")

        result = self._detector.detect(minimap, region, region_offset=(x1, y1))

        if result.success:
            # 传送检测
            if self._position and result.position:
                dist = ((result.position[0] - self._position[0]) ** 2 +
                        (result.position[1] - self._position[1]) ** 2) ** 0.5
                if dist > self._config.teleport_threshold:
                    logger.warning("Teleport detected (%.0f px), re-scanning", dist)
                    self._change_state(TrackingState.GLOBAL_SCAN)
                    return self._build_status(f"Teleport detected ({dist:.0f} px)")

            # EMA 平滑后赋值
            if result.position is not None:
                smoothed = self._smooth_position(result.position[0], result.position[1])
                self._position = smoothed
            else:
                self._position = result.position
            self._confidence = result.confidence
            self._lost_frames = 0

            # Update direction from arrow detector (precise)
            if result.direction != 0.0:
                self._direction = result.direction

            # Fallback: compute direction from displacement
            if self._prev_position is not None and result.position is not None:
                dx = result.position[0] - self._prev_position[0]
                dy = result.position[1] - self._prev_position[1]
                dist_moved = (dx * dx + dy * dy) ** 0.5
                if dist_moved > 3.0 and result.direction == 0.0:
                    # atan2 gives angle from positive X axis, convert to compass bearing
                    # In pixel coords: x=right, y=down
                    # 0=north(up), 90=east(right), 180=south(down), 270=west(left)
                    self._direction = (math.degrees(math.atan2(dx, -dy))) % 360
            if result.position is not None:
                self._prev_position = result.position

            self._notify_position()
            return self._build_status(
                f"Tracking: ({self._position[0]:.0f}, {self._position[1]:.0f}) "
                f"conf={self._confidence:.2f}"
            )
        else:
            self._lost_frames += 1
            if self._lost_frames > self._config.max_lost_frames:
                self._change_state(TrackingState.INERTIA_NAV)
                return self._build_status("Too many lost frames, entering inertia mode")
            return self._build_status(f"Lost frame {self._lost_frames}/{self._config.max_lost_frames}")

    def _do_inertia_nav(self, minimap) -> TrackingStatus:
        """
        惯性导航: 使用运动预测，同时尝试恢复追踪
        """
        self._lost_frames += 1

        # 尝试在更大范围恢复
        if self._position:
            px, py = self._position
            radius = self._config.tracking_radius * 2
            recovered = False

            # 优先使用预计算特征恢复（更快）
            if self._detector._sift_matcher.is_precomputed:
                minimap_gray = self._detector._image_processor.preprocess_minimap(
                    minimap, self._detector._use_clahe, self._detector._use_ring_mask,
                    self._detector._ring_outer, self._detector._ring_inner)
                minimap_mask = None
                if self._detector._use_ring_mask:
                    h, w = minimap_gray.shape[:2]
                    minimap_mask = self._detector._image_processor.create_ring_mask(
                        min(h, w), self._detector._ring_outer, self._detector._ring_inner)
                result_sift = self._detector._sift_matcher.match_precomputed(
                    minimap_gray,
                    search_center=self._position,
                    search_radius=radius,
                    minimap_mask=minimap_mask)
                if result_sift.success:
                    # EMA 平滑后恢复
                    if result_sift.position is not None:
                        smoothed = self._smooth_position(result_sift.position[0], result_sift.position[1])
                        self._position = smoothed
                    else:
                        self._position = result_sift.position
                    self._confidence = result_sift.confidence
                    recovered = True
            else:
                # Fallback: region-based 恢复
                x1 = int(max(0, px - radius))
                y1 = int(max(0, py - radius))
                region = self._map_manager.get_logic_region(x1, y1, radius * 2, radius * 2, copy=False)
                if region is not None:
                    result = self._detector.detect(minimap, region, region_offset=(x1, y1))
                    if result.success:
                        # EMA 平滑后恢复
                        if result.position is not None:
                            smoothed = self._smooth_position(result.position[0], result.position[1])
                            self._position = smoothed
                        else:
                            self._position = result.position
                        self._confidence = result.confidence
                        recovered = True

            if recovered:
                self._lost_frames = 0
                self._change_state(TrackingState.PRECISE_TRACK)
                self._notify_position()
                return self._build_status("Recovered from inertia mode")

        # 超过最大惯性帧数，重新全局扫描
        if self._lost_frames > self._config.max_inertia_frames:
            self._change_state(TrackingState.GLOBAL_SCAN)
            return self._build_status("Inertia timeout, re-scanning")

        self._confidence = max(0.0, self._confidence - 0.01)
        return self._build_status(
            f"Inertia nav: frame {self._lost_frames}/{self._config.max_inertia_frames}"
        )

    # ==================== 辅助方法 ====================

    def _capture_minimap(self) -> Optional['numpy.ndarray']:
        """截取小地图区域"""
        if self._minimap_region is None:
            return None
        return self._capture.capture_minimap_region(self._minimap_region)

    def _change_state(self, new_state: TrackingState):
        old_state = self._state
        self._state = new_state
        if old_state != new_state:
            logger.info("Tracking state: %s -> %s", old_state.value, new_state.value)
            if self._on_state_change:
                self._on_state_change(new_state)

    def _notify_position(self):
        if self._on_position_update and self._position:
            self._on_position_update(
                self._position[0], self._position[1],
                self._direction, self._confidence
            )

    def _build_status(self, detail: str = "") -> TrackingStatus:
        return TrackingStatus(
            state=self._state,
            position=self._position,
            direction=self._direction,
            confidence=self._confidence,
            fps=self._fps,
            lost_frames=self._lost_frames,
            detail=detail
        )

    # ==================== 属性 ====================

    @property
    def state(self) -> TrackingState:
        return self._state

    @property
    def position(self) -> Optional[Tuple[float, float]]:
        return self._position

    @property
    def direction(self) -> float:
        return self._direction

    @property
    def confidence(self) -> float:
        return self._confidence

    def get_status(self) -> TrackingStatus:
        return self._build_status()

    def precompute_map_features(self, map_gray) -> int:
        """
        Pre-compute SIFT features for the world map.

        Delegates to MinimapDetector.precompute_map() which applies
        CLAHE preprocessing before feature extraction.

        Args:
            map_gray: Grayscale world map image

        Returns:
            Number of features extracted
        """
        return self._detector.precompute_map(map_gray)
