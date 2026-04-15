"""
小地图检测器

集成 SIFT 特征匹配、CLAHE 增强、圆环遮罩、颜色检测等
多策略定位方案。支持可见性检测和自动降级。
"""

import logging
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum

from roco_navigator.vision.image_processor import ImageProcessor
from roco_navigator.vision.sift_matcher import SIFTMatcher, MatchResult
from roco_navigator.vision.color_detector import ColorDetector, ColorDetectResult
from roco_navigator.vision.template_matcher import TemplateMatcher

logger = logging.getLogger(__name__)


class DetectionStrategy(Enum):
    """检测策略"""
    SIFT = "sift"              # SIFT 特征匹配 (默认)
    COLOR = "color"            # 颜色检测 (降级)
    PREDICTION = "prediction"  # 运动预测 (最终降级)


@dataclass
class DetectionResult:
    """检测结果"""
    success: bool
    position: Optional[Tuple[float, float]] = None  # (x, y) 世界坐标
    strategy: DetectionStrategy = DetectionStrategy.SIFT
    confidence: float = 0.0
    minimap_visible: bool = True
    details: str = ""


@dataclass
class PositionHistory:
    """位置历史记录"""
    positions: List[Tuple[float, float]] = field(default_factory=list)
    max_size: int = 20

    def add(self, pos: Tuple[float, float]):
        self.positions.append(pos)
        if len(self.positions) > self.max_size:
            self.positions.pop(0)

    def predict_next(self) -> Optional[Tuple[float, float]]:
        """基于历史位置线性预测下一个位置"""
        if len(self.positions) < 2:
            return self.positions[-1] if self.positions else None

        p1 = self.positions[-2]
        p2 = self.positions[-1]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return (p2[0] + dx, p2[1] + dy)

    @property
    def last(self) -> Optional[Tuple[float, float]]:
        return self.positions[-1] if self.positions else None

    def clear(self):
        self.positions.clear()


class MinimapDetector:
    """
    小地图检测器

    多策略定位:
    1. SIFT 特征匹配 (主要方案)
    2. 颜色检测 (降级方案)
    3. 运动预测 (最终降级)

    包含:
    - CLAHE 图像增强
    - 圆环遮罩去噪
    - 小地图可见性检测
    - 位置历史和预测
    """

    def __init__(self,
                 use_clahe: bool = True,
                 use_ring_mask: bool = True,
                 use_gpu: bool = False,
                 sift_ratio: float = 0.7,
                 min_matches: int = 10,
                 ring_outer: float = 0.95,
                 ring_inner: float = 0.0):
        """
        初始化小地图检测器

        Args:
            use_clahe: 启用 CLAHE 增强
            use_ring_mask: 启用圆环遮罩
            use_gpu: 启用 GPU 加速
            sift_ratio: SIFT ratio test 阈值
            min_matches: 最少匹配点
            ring_outer: 圆环外径比例
            ring_inner: 圆环内径比例
        """
        # 配置
        self._use_clahe = use_clahe
        self._use_ring_mask = use_ring_mask
        self._ring_outer = ring_outer
        self._ring_inner = ring_inner

        # 子模块
        self._image_processor = ImageProcessor(use_gpu=use_gpu)
        self._sift_matcher = SIFTMatcher(
            ratio_threshold=sift_ratio,
            min_good_matches=min_matches
        )
        self._color_detector = ColorDetector(preset="player_red")
        self._template_matcher = TemplateMatcher(use_gpu=use_gpu)

        # 状态
        self._history = PositionHistory()
        self._minimap_template: Optional[np.ndarray] = None  # 小地图边框模板
        self._hidden_count = 0
        self._hidden_threshold = 5

        # 可见性检测参数
        self._visibility_edge_ratio = 0.05
        self._visibility_std_threshold = 15

        logger.info(
            "MinimapDetector initialized (CLAHE=%s, RingMask=%s, GPU=%s)",
            use_clahe, use_ring_mask, use_gpu
        )

    # ==================== 主检测接口 ====================

    def detect(self, minimap_bgr: np.ndarray,
               map_region_bgr: np.ndarray,
               region_offset: Tuple[int, int] = (0, 0)
               ) -> DetectionResult:
        """
        检测玩家在世界地图中的位置

        多策略检测:
        1. 检查小地图是否可见
        2. SIFT 特征匹配
        3. 降级到颜色检测
        4. 降级到运动预测

        Args:
            minimap_bgr: 小地图截图 (BGR)
            map_region_bgr: 世界地图搜索区域 (BGR)
            region_offset: 搜索区域偏移 (x, y)

        Returns:
            DetectionResult
        """
        # Step 0: 检查小地图可见性
        if not self.is_minimap_visible(minimap_bgr):
            self._hidden_count += 1
            if self._hidden_count > self._hidden_threshold:
                return DetectionResult(
                    success=False,
                    position=self._history.last,
                    minimap_visible=False,
                    details="Minimap hidden (backpack/battle?)"
                )
            # 短暂隐藏，使用预测
            predicted = self._history.predict_next()
            return DetectionResult(
                success=predicted is not None,
                position=predicted,
                strategy=DetectionStrategy.PREDICTION,
                confidence=0.3,
                minimap_visible=False,
                details="Minimap temporarily hidden, using prediction"
            )

        # 小地图可见，重置计数
        self._hidden_count = 0

        # Step 1: 预处理
        minimap_gray = self._image_processor.preprocess_minimap(
            minimap_bgr,
            use_clahe=self._use_clahe,
            use_ring_mask=self._use_ring_mask,
            outer_ratio=self._ring_outer,
            inner_ratio=self._ring_inner
        )
        region_gray = self._image_processor.preprocess_map_region(
            map_region_bgr,
            use_clahe=self._use_clahe
        )

        # 获取遮罩 (用于 SIFT)
        minimap_mask = None
        if self._use_ring_mask:
            h, w = minimap_gray.shape[:2]
            minimap_mask = self._image_processor.create_ring_mask(
                min(h, w), self._ring_outer, self._ring_inner
            )

        # Step 2: SIFT 特征匹配
        sift_result = self._sift_matcher.match(
            minimap_gray, region_gray,
            minimap_mask=minimap_mask,
            region_offset=region_offset
        )

        if sift_result.success and self._validate_position(sift_result.position):
            self._history.add(sift_result.position)
            return DetectionResult(
                success=True,
                position=sift_result.position,
                strategy=DetectionStrategy.SIFT,
                confidence=sift_result.confidence,
                details=f"SIFT match: {sift_result.good_matches} matches, "
                        f"{sift_result.inliers} inliers"
            )

        # Step 3: 颜色检测降级
        color_result = self._color_detector.detect(minimap_bgr)
        if color_result.found:
            # 颜色检测得到的是小地图坐标，需要转换
            # 这里简化处理：如果有历史位置，在附近搜索
            if self._history.last:
                return DetectionResult(
                    success=True,
                    position=self._history.last,
                    strategy=DetectionStrategy.COLOR,
                    confidence=color_result.confidence * 0.5,
                    details="Color detection (approximate)"
                )

        # Step 4: 运动预测降级
        predicted = self._history.predict_next()
        if predicted:
            return DetectionResult(
                success=True,
                position=predicted,
                strategy=DetectionStrategy.PREDICTION,
                confidence=0.2,
                details="Motion prediction fallback"
            )

        return DetectionResult(
            success=False,
            details="All detection strategies failed"
        )

    # ==================== 可见性检测 ====================

    def is_minimap_visible(self, minimap_region: np.ndarray) -> bool:
        """
        检测小地图是否可见

        当打开背包、进入战斗时小地图会被遮挡。
        通过检测图像特征来判断小地图是否可见。

        方法:
        1. 边缘密度检测 (小地图有丰富的边缘)
        2. 颜色标准差 (纯色/黑屏说明被遮挡)
        3. 模板匹配 (检测小地图边框)

        Args:
            minimap_region: 小地图区域截图 (BGR)

        Returns:
            bool: 小地图是否可见
        """
        if minimap_region is None or minimap_region.size == 0:
            return False

        # 方法 1: 颜色标准差
        std = np.std(minimap_region)
        if std < self._visibility_std_threshold:
            logger.debug("Minimap hidden: low color variance (std=%.1f)", std)
            return False

        # 方法 2: 边缘密度
        gray = cv2.cvtColor(minimap_region, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = np.count_nonzero(edges) / edges.size

        if edge_ratio < self._visibility_edge_ratio:
            logger.debug("Minimap hidden: low edge density (%.3f)", edge_ratio)
            return False

        # 方法 3: 模板匹配 (如果有模板)
        if self._minimap_template is not None:
            result = self._template_matcher.match_template(
                gray, self._minimap_template, threshold=0.6
            )
            if not result.found:
                logger.debug("Minimap hidden: template not matched")
                return False

        return True

    def calibrate_visibility_template(self, minimap_image: np.ndarray):
        """
        校准小地图可见性模板

        截取小地图的边框特征作为可见性检测的模板

        Args:
            minimap_image: 已知可见状态的小地图截图 (BGR)
        """
        gray = cv2.cvtColor(minimap_image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        # 提取上边缘作为模板
        border = max(5, h // 20)
        self._minimap_template = gray[0:border, :].copy()
        logger.info("Minimap visibility template calibrated (%dx%d)", w, border)

    # ==================== 位置验证 ====================

    def _validate_position(self, position: Optional[Tuple[float, float]]) -> bool:
        """
        验证检测到的位置是否合理

        检查:
        - 是否为 None
        - 移动速度是否合理 (防止跳变)

        Args:
            position: 检测到的位置

        Returns:
            bool: 位置是否有效
        """
        if position is None:
            return False

        if self._history.last is None:
            return True  # 第一次检测，接受任何位置

        # 检查移动距离
        last = self._history.last
        dx = position[0] - last[0]
        dy = position[1] - last[1]
        distance = (dx ** 2 + dy ** 2) ** 0.5

        max_speed = 150  # 最大合理移动距离 (像素/帧)
        if distance > max_speed:
            logger.warning(
                "Position jump detected: %.1f pixels (max=%d)",
                distance, max_speed
            )
            return False

        return True

    # ==================== 公共方法 ====================

    def reset(self):
        """重置检测器状态"""
        self._history.clear()
        self._hidden_count = 0
        self._sift_matcher.reset_stats()
        logger.info("MinimapDetector reset")

    def get_stats(self) -> dict:
        """获取检测统计"""
        sift_stats = self._sift_matcher.get_stats()
        return {
            "sift": sift_stats,
            "history_size": len(self._history.positions),
            "hidden_count": self._hidden_count,
            "last_position": self._history.last,
        }

    @property
    def last_position(self) -> Optional[Tuple[float, float]]:
        return self._history.last

    @property
    def position_history(self) -> List[Tuple[float, float]]:
        return self._history.positions.copy()
