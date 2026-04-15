"""
颜色检测器

通过 HSV 颜色空间检测小地图中的玩家标记。
作为 SIFT 匹配的降级方案。
"""

import logging
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ColorDetectResult:
    """颜色检测结果"""
    found: bool
    position: Optional[Tuple[int, int]] = None  # (x, y) 在图像中的位置
    area: float = 0.0
    confidence: float = 0.0


class ColorDetector:
    """
    颜色检测器

    在小地图中通过颜色检测玩家标记点。
    适用于玩家图标有明确颜色特征的情况。
    作为 SIFT 匹配的降级方案。
    """

    # 预定义颜色范围 (HSV)
    # 注意: OpenCV 的 H 范围是 0-179, S 和 V 是 0-255
    COLOR_PRESETS = {
        # 玩家标记 (红色箭头)
        "player_red": {
            "lower1": np.array([0, 150, 150]),
            "upper1": np.array([10, 255, 255]),
            "lower2": np.array([170, 150, 150]),
            "upper2": np.array([179, 255, 255]),
        },
        # 玩家标记 (绿色)
        "player_green": {
            "lower1": np.array([35, 150, 150]),
            "upper1": np.array([85, 255, 255]),
        },
        # 玩家标记 (蓝色)
        "player_blue": {
            "lower1": np.array([100, 150, 150]),
            "upper1": np.array([130, 255, 255]),
        },
        # 玩家标记 (白色/高亮)
        "player_white": {
            "lower1": np.array([0, 0, 220]),
            "upper1": np.array([179, 30, 255]),
        },
    }

    def __init__(self, preset: str = "player_red"):
        """
        初始化颜色检测器

        Args:
            preset: 预设颜色名称
        """
        self._preset = preset
        self._min_area = 10        # 最小轮廓面积
        self._max_area = 5000      # 最大轮廓面积
        self._morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (3, 3)
        )

        logger.debug("ColorDetector initialized (preset=%s)", preset)

    def detect(self, image: np.ndarray,
               preset: Optional[str] = None) -> ColorDetectResult:
        """
        在图像中检测指定颜色的目标

        Args:
            image: BGR 格式图像
            preset: 颜色预设名称，None 使用默认

        Returns:
            ColorDetectResult
        """
        preset_name = preset or self._preset
        color_range = self.COLOR_PRESETS.get(preset_name)

        if color_range is None:
            logger.warning("Unknown color preset: %s", preset_name)
            return ColorDetectResult(found=False)

        # 转换到 HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # 创建颜色掩膜
        mask = cv2.inRange(hsv, color_range["lower1"], color_range["upper1"])

        # 处理红色等跨越 0 度的颜色 (需要两个范围)
        if "lower2" in color_range:
            mask2 = cv2.inRange(hsv, color_range["lower2"], color_range["upper2"])
            mask = cv2.bitwise_or(mask, mask2)

        # 形态学处理 (去噪)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._morph_kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._morph_kernel)

        # 查找轮廓
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return ColorDetectResult(found=False)

        # 过滤并找到最大的符合条件的轮廓
        valid_contours = [
            c for c in contours
            if self._min_area <= cv2.contourArea(c) <= self._max_area
        ]

        if not valid_contours:
            return ColorDetectResult(found=False)

        largest = max(valid_contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        # 计算质心
        M = cv2.moments(largest)
        if M["m00"] == 0:
            return ColorDetectResult(found=False)

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # 置信度基于面积和形状
        confidence = min(1.0, area / 200.0)

        return ColorDetectResult(
            found=True,
            position=(cx, cy),
            area=area,
            confidence=confidence
        )

    def detect_all(self, image: np.ndarray,
                   preset: Optional[str] = None
                   ) -> List[ColorDetectResult]:
        """
        检测所有颜色目标

        Args:
            image: BGR 格式图像
            preset: 颜色预设

        Returns:
            所有检测到的目标列表
        """
        preset_name = preset or self._preset
        color_range = self.COLOR_PRESETS.get(preset_name)
        if color_range is None:
            return []

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, color_range["lower1"], color_range["upper1"])
        if "lower2" in color_range:
            mask2 = cv2.inRange(hsv, color_range["lower2"], color_range["upper2"])
            mask = cv2.bitwise_or(mask, mask2)

        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._morph_kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self._min_area or area > self._max_area:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            results.append(ColorDetectResult(
                found=True,
                position=(cx, cy),
                area=area,
                confidence=min(1.0, area / 200.0)
            ))

        return results

    def set_color_range(self, name: str,
                        lower: Tuple[int, int, int],
                        upper: Tuple[int, int, int],
                        lower2: Optional[Tuple[int, int, int]] = None,
                        upper2: Optional[Tuple[int, int, int]] = None):
        """
        自定义颜色范围

        Args:
            name: 预设名称
            lower: HSV 下限
            upper: HSV 上限
            lower2: 可选的第二段 HSV 下限 (用于跨越 0 度的颜色)
            upper2: 可选的第二段 HSV 上限
        """
        preset = {
            "lower1": np.array(lower),
            "upper1": np.array(upper),
        }
        if lower2 is not None and upper2 is not None:
            preset["lower2"] = np.array(lower2)
            preset["upper2"] = np.array(upper2)

        self.COLOR_PRESETS[name] = preset
        logger.info("Custom color range added: %s", name)

    def set_area_range(self, min_area: float, max_area: float):
        """设置面积过滤范围"""
        self._min_area = min_area
        self._max_area = max_area
