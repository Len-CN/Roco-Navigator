"""
导航模块

管理导航状态、目标切换、方向计算、进度跟踪。
"""

import logging
import math
import time
from typing import Optional, Tuple, List, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NavigationState(Enum):
    """导航状态"""
    IDLE = "idle"
    NAVIGATING = "navigating"
    ARRIVED = "arrived"
    PAUSED = "paused"


@dataclass
class NavigationInfo:
    """导航信息"""
    state: NavigationState
    current_target: Optional[Tuple[float, float]]
    current_target_index: int
    total_targets: int
    distance_to_target: float
    direction_to_target: float       # 角度 (0=北, 顺时针)
    direction_text: str              # "北", "东北", ...
    progress: float                  # 0.0 - 1.0
    eta_seconds: float               # 预计到达时间
    target_name: str


class Navigator:
    """
    导航器

    功能:
    - 沿路线导航
    - 到达判定和自动切换目标
    - 方向指示
    - 进度计算
    - ETA 估算
    """

    def __init__(self,
                 arrival_distance: float = 20.0,
                 speed_estimate: float = 5.0):
        """
        Args:
            arrival_distance: 到达判定距离 (像素)
            speed_estimate: 移动速度估计 (像素/秒)
        """
        self._arrival_distance = arrival_distance
        self._speed_estimate = speed_estimate

        # 状态
        self._state = NavigationState.IDLE
        self._route: List[Tuple[float, float]] = []
        self._target_names: List[str] = []
        self._current_index: int = 0
        self._player_pos: Optional[Tuple[float, float]] = None
        self._visited: set = set()  # indices of visited targets

        # 速度估算
        self._last_pos: Optional[Tuple[float, float]] = None
        self._last_time: float = 0.0
        self._speed_samples: List[float] = []
        self._max_speed_samples: int = 20

        # 回调
        self._on_target_reached: Optional[Callable] = None
        self._on_navigation_complete: Optional[Callable] = None

        logger.info("Navigator initialized (arrival=%.0f, speed=%.1f)",
                     arrival_distance, speed_estimate)

    # ==================== 控制 ====================

    def start(self, route: List[Tuple[float, float]],
              target_names: Optional[List[str]] = None,
              start_index: int = 0):
        """
        开始导航

        Args:
            route: 路线点列表 (第 0 个是起点，从第 1 个开始导航)
            target_names: 各点名称
            start_index: 从第几个目标开始 (默认跳过起点)
        """
        if len(route) < 2:
            logger.warning("Route too short to navigate")
            return

        self._route = list(route)
        self._current_index = max(1, start_index)  # 至少从 1 开始 (跳过起点)
        self._state = NavigationState.NAVIGATING
        self._speed_samples.clear()
        self._visited.clear()

        if target_names:
            self._target_names = list(target_names)
        else:
            self._target_names = [f"点位 {i}" for i in range(len(route))]

        logger.info("Navigation started: %d targets", len(route) - 1)

    def stop(self):
        """停止导航"""
        if self._state == NavigationState.IDLE and not self._route:
            return
        self._state = NavigationState.IDLE
        self._route = []
        self._current_index = 0
        logger.info("Navigation stopped")

    def pause(self):
        """暂停导航"""
        if self._state == NavigationState.NAVIGATING:
            self._state = NavigationState.PAUSED

    def resume(self):
        """恢复导航"""
        if self._state == NavigationState.PAUSED:
            self._state = NavigationState.NAVIGATING

    def skip_target(self):
        """跳过当前目标"""
        if self._state == NavigationState.NAVIGATING:
            self._advance_target()

    def jump_to(self, index: int):
        """跳转到指定路线点，将之前所有未访问目标标记为已到达"""
        if self._state != NavigationState.NAVIGATING:
            return
        if index < 1 or index >= len(self._route):
            return
        if index <= self._current_index:
            return
        skipped = index - self._current_index
        for i in range(self._current_index, index):
            self._visited.add(i)
        self._current_index = index
        logger.info("Jumped to target %d/%d, marked %d targets as visited",
                    index, len(self._route) - 1, skipped)

    # ==================== 更新 ====================

    def update(self, player_x: float, player_y: float) -> NavigationInfo:
        """
        更新导航状态

        Args:
            player_x, player_y: 当前玩家位置

        Returns:
            NavigationInfo
        """
        self._player_pos = (player_x, player_y)
        self._update_speed(player_x, player_y)

        if self._state != NavigationState.NAVIGATING:
            return self._build_info()

        if self._current_index >= len(self._route):
            self._state = NavigationState.ARRIVED
            if self._on_navigation_complete:
                self._on_navigation_complete()
            return self._build_info()

        target = self._route[self._current_index]
        dist = self._distance_to(player_x, player_y, target)

        # 到达判定
        if dist <= self._arrival_distance:
            logger.info("Target %d reached (dist=%.1f)", self._current_index, dist)
            if self._on_target_reached:
                self._on_target_reached(self._current_index, target)
            self._advance_target()

        return self._build_info()

    def _advance_target(self):
        """前进到下一个目标"""
        self._visited.add(self._current_index)  # mark current target as visited
        self._current_index += 1
        if self._current_index >= len(self._route):
            self._state = NavigationState.ARRIVED
            logger.info("All targets reached, navigation complete")
            if self._on_navigation_complete:
                self._on_navigation_complete()
        else:
            logger.info("Advancing to target %d/%d",
                         self._current_index, len(self._route) - 1)

    def _update_speed(self, x: float, y: float):
        """更新速度估算"""
        now = time.perf_counter()
        if self._last_pos and self._last_time > 0:
            dt = now - self._last_time
            if dt > 0:
                dist = self._distance_to(x, y, self._last_pos)
                speed = dist / dt
                if 0 < speed < 500:  # 过滤异常值
                    self._speed_samples.append(speed)
                    if len(self._speed_samples) > self._max_speed_samples:
                        self._speed_samples.pop(0)
                    self._speed_estimate = (
                        sum(self._speed_samples) / len(self._speed_samples)
                    )
        self._last_pos = (x, y)
        self._last_time = now

    # ==================== 计算 ====================

    def _distance_to(self, x: float, y: float,
                     target: Tuple[float, float]) -> float:
        return math.sqrt((target[0] - x) ** 2 + (target[1] - y) ** 2)

    def _direction_to(self, x: float, y: float,
                      target: Tuple[float, float]) -> float:
        """计算方向角 (0=北, 顺时针, 度)"""
        dx = target[0] - x
        dy = target[1] - y
        angle = math.degrees(math.atan2(dx, -dy))
        if angle < 0:
            angle += 360
        return angle

    @staticmethod
    def _direction_text(angle: float) -> str:
        directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        idx = round(angle / 45) % 8
        return directions[idx]

    def _build_info(self) -> NavigationInfo:
        if not self._route or self._current_index >= len(self._route):
            return NavigationInfo(
                state=self._state,
                current_target=None,
                current_target_index=self._current_index,
                total_targets=max(0, len(self._route) - 1),
                distance_to_target=0,
                direction_to_target=0,
                direction_text="--",
                progress=1.0 if self._state == NavigationState.ARRIVED else 0.0,
                eta_seconds=0,
                target_name="",
            )

        target = self._route[self._current_index]
        px, py = self._player_pos or (0, 0)

        dist = self._distance_to(px, py, target)
        direction = self._direction_to(px, py, target)
        dir_text = self._direction_text(direction)

        total_targets = len(self._route) - 1
        progress = (self._current_index - 1) / max(1, total_targets)

        eta = dist / max(0.1, self._speed_estimate)

        name_idx = min(self._current_index, len(self._target_names) - 1)
        target_name = self._target_names[name_idx] if self._target_names else ""

        return NavigationInfo(
            state=self._state,
            current_target=target,
            current_target_index=self._current_index,
            total_targets=total_targets,
            distance_to_target=dist,
            direction_to_target=direction,
            direction_text=dir_text,
            progress=progress,
            eta_seconds=eta,
            target_name=target_name,
        )

    # ==================== 回调 ====================

    def set_on_target_reached(self, callback: Callable):
        self._on_target_reached = callback

    def set_on_navigation_complete(self, callback: Callable):
        self._on_navigation_complete = callback

    # ==================== 属性 ====================

    @property
    def state(self) -> NavigationState:
        return self._state

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_target(self) -> Optional[Tuple[float, float]]:
        if self._route and self._current_index < len(self._route):
            return self._route[self._current_index]
        return None

    @property
    def route(self) -> List[Tuple[float, float]]:
        return self._route.copy()

    @property
    def is_active(self) -> bool:
        return self._state == NavigationState.NAVIGATING

    @property
    def visited_indices(self) -> set:
        return self._visited.copy()
