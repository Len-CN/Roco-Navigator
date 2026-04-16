"""
地图数据管理

负责加载世界地图、维护双地图架构 (逻辑地图 + 显示地图)、坐标转换。
"""

import logging
import os
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

from roco_navigator.utils.file_utils import get_assets_dir

logger = logging.getLogger(__name__)


@dataclass
class MapInfo:
    """地图信息"""
    map_id: str
    name: str
    width: int
    height: int
    image_path: str


class MapManager:
    """
    地图管理器

    双地图架构:
    - logic_map: 纯净底图，用于 SIFT 特征匹配 (无标记)
    - display_map: 带标记底图，用于 UI 显示

    坐标系:
    - 世界坐标 (world): 地图像素坐标
    - 小地图坐标 (minimap): 小地图截图内坐标
    - 屏幕坐标 (screen): UI 显示坐标
    """

    def __init__(self):
        self._maps_dir = os.path.join(get_assets_dir(), "maps")

        # 当前地图
        self._current_map_id: Optional[str] = None
        self._logic_map: Optional[np.ndarray] = None
        self._display_map: Optional[np.ndarray] = None
        self._map_width: int = 0
        self._map_height: int = 0

        # 地图列表
        self._available_maps: List[MapInfo] = []

        # 小地图参数
        self._minimap_scale: float = 1.0  # 小地图像素到世界像素的比例

        logger.info("MapManager initialized")

    # ==================== 地图加载 ====================

    def load_map(self, map_path: str, map_id: str = "default") -> bool:
        """
        加载地图图像

        Args:
            map_path: 地图图像文件路径
            map_id: 地图 ID

        Returns:
            bool: 是否成功加载
        """
        if not os.path.exists(map_path):
            logger.error("Map file not found: %s", map_path)
            return False

        try:
            img = cv2.imread(map_path)
            if img is None:
                logger.error("Failed to read map image: %s", map_path)
                return False

            self._logic_map = img.copy()
            self._display_map = img.copy()
            self._map_height, self._map_width = img.shape[:2]
            self._current_map_id = map_id

            logger.info("Map loaded: %s (%dx%d)", map_id, self._map_width, self._map_height)
            return True
        except Exception as e:
            logger.error("Error loading map: %s", e)
            return False

    def load_map_from_array(self, image: np.ndarray, map_id: str = "default") -> bool:
        """从 numpy 数组加载地图"""
        if image is None or image.size == 0:
            return False

        self._logic_map = image.copy()
        self._display_map = image.copy()
        self._map_height, self._map_width = image.shape[:2]
        self._current_map_id = map_id
        logger.info("Map loaded from array: %s (%dx%d)", map_id, self._map_width, self._map_height)
        return True

    # ==================== 地图区域获取 ====================

    def get_logic_region(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """
        获取逻辑地图区域 (用于 SIFT 匹配)

        Args:
            x, y: 左上角世界坐标
            w, h: 区域尺寸

        Returns:
            地图区域图像 (BGR)
        """
        if self._logic_map is None:
            return None

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(self._map_width, x + w)
        y2 = min(self._map_height, y + h)

        if x2 <= x1 or y2 <= y1:
            return None

        return self._logic_map[y1:y2, x1:x2].copy()

    def get_display_region(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """获取显示地图区域 (用于 HUD 显示)"""
        if self._display_map is None:
            return None

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(self._map_width, x + w)
        y2 = min(self._map_height, y + h)

        if x2 <= x1 or y2 <= y1:
            return None

        return self._display_map[y1:y2, x1:x2].copy()

    def get_map_crop_centered(self, center_x: float, center_y: float,
                              crop_size: int = 600) -> Tuple[Optional[np.ndarray], Tuple[float, float]]:
        """
        获取以指定点为中心的地图裁剪 (用于 HUD)

        Args:
            center_x, center_y: 中心世界坐标
            crop_size: 裁剪尺寸

        Returns:
            (裁剪图像, 玩家在裁剪中的相对坐标)
        """
        if self._display_map is None:
            return None, (0, 0)

        half = crop_size // 2
        x1 = int(max(0, center_x - half))
        y1 = int(max(0, center_y - half))
        x2 = int(min(self._map_width, center_x + half))
        y2 = int(min(self._map_height, center_y + half))

        crop = self._display_map[y1:y2, x1:x2].copy()

        # 玩家在裁剪图中的相对位置
        rel_x = center_x - x1
        rel_y = center_y - y1

        return crop, (rel_x, rel_y)

    # ==================== 坐标转换 ====================

    def minimap_to_world(self, minimap_x: float, minimap_y: float,
                         minimap_size: int,
                         player_world_x: float, player_world_y: float
                         ) -> Tuple[float, float]:
        """
        小地图坐标转世界坐标

        小地图中心 = 玩家当前世界位置

        Args:
            minimap_x, minimap_y: 小地图中的坐标
            minimap_size: 小地图尺寸
            player_world_x, player_world_y: 玩家当前世界坐标

        Returns:
            (world_x, world_y)
        """
        center = minimap_size / 2.0
        dx = (minimap_x - center) * self._minimap_scale
        dy = (minimap_y - center) * self._minimap_scale
        return (player_world_x + dx, player_world_y + dy)

    def world_to_minimap(self, world_x: float, world_y: float,
                         minimap_size: int,
                         player_world_x: float, player_world_y: float
                         ) -> Tuple[float, float]:
        """世界坐标转小地图坐标"""
        center = minimap_size / 2.0
        dx = (world_x - player_world_x) / self._minimap_scale
        dy = (world_y - player_world_y) / self._minimap_scale
        return (center + dx, center + dy)

    def set_minimap_scale(self, scale: float):
        """设置小地图比例尺"""
        self._minimap_scale = scale
        logger.info("Minimap scale set to %.2f", scale)

    # ==================== 属性 ====================

    @property
    def is_loaded(self) -> bool:
        return self._logic_map is not None

    @property
    def map_width(self) -> int:
        return self._map_width

    @property
    def map_height(self) -> int:
        return self._map_height

    @property
    def current_map_id(self) -> Optional[str]:
        return self._current_map_id

    @property
    def logic_map(self) -> Optional[np.ndarray]:
        return self._logic_map

    @property
    def display_map(self) -> Optional[np.ndarray]:
        return self._display_map

    @property
    def available_maps(self) -> List[MapInfo]:
        return self._available_maps
