"""
图像预处理模块

提供 CLAHE 增强、圆环遮罩、颜色空间转换等图像处理功能。
支持可选的 GPU 加速。
"""

import logging
import cv2
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ImageProcessor:
    """图像处理器"""

    def __init__(self, use_gpu: bool = False):
        self._use_gpu = use_gpu

        # CLAHE 增强器
        self._clahe = cv2.createCLAHE(
            clipLimit=3.0,
            tileGridSize=(8, 8)
        )

        # 缓存的圆环遮罩
        self._mask_cache: dict = {}

        logger.debug("ImageProcessor initialized (GPU=%s)", use_gpu)

    # ==================== CLAHE 增强 ====================

    def apply_clahe(self, image: np.ndarray, clip_limit: float = 3.0,
                    tile_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
        """
        使用 CLAHE 增强图像对比度

        特别适用于大面积纯色区域 (水面、草原、沙漠)，
        能显著增加这些区域的特征点数量。

        Args:
            image: 输入图像 (BGR 或灰度)
            clip_limit: 对比度限制
            tile_size: 分块大小

        Returns:
            增强后的灰度图像
        """
        # 如果参数不同于默认，创建新的 CLAHE 实例
        if clip_limit != 3.0 or tile_size != (8, 8):
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_size)
        else:
            clahe = self._clahe

        # 转灰度
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        enhanced = clahe.apply(gray)
        return enhanced

    # ==================== 圆环遮罩 ====================

    def create_ring_mask(self, size: int,
                         outer_ratio: float = 0.95,
                         inner_ratio: float = 0.0) -> np.ndarray:
        """
        创建圆环遮罩

        去除小地图中心的玩家图标干扰和边角的 UI 元素，
        提高特征匹配的准确率。

        Args:
            size: 图像尺寸 (正方形)
            outer_ratio: 外圆半径占图像尺寸的比例 (去除边角)
            inner_ratio: 内圆半径占图像尺寸的比例 (去除中心玩家图标)

        Returns:
            np.ndarray: 二值遮罩 (255=保留, 0=遮挡)
        """
        cache_key = (size, outer_ratio, inner_ratio)
        if cache_key in self._mask_cache:
            return self._mask_cache[cache_key]

        mask = np.zeros((size, size), dtype=np.uint8)
        center = (size // 2, size // 2)

        outer_radius = int(size * outer_ratio / 2)
        inner_radius = int(size * inner_ratio / 2)

        # 绘制外圆 (白色 = 保留)
        cv2.circle(mask, center, outer_radius, 255, -1)

        # 去掉内圆 (黑色 = 遮挡)
        if inner_radius > 0:
            cv2.circle(mask, center, inner_radius, 0, -1)

        self._mask_cache[cache_key] = mask
        return mask

    def apply_ring_mask(self, image: np.ndarray,
                        outer_ratio: float = 0.95,
                        inner_ratio: float = 0.0) -> np.ndarray:
        """
        对图像应用圆环遮罩

        Args:
            image: 输入图像
            outer_ratio: 外圆比例
            inner_ratio: 内圆比例

        Returns:
            遮罩后的图像
        """
        h, w = image.shape[:2]
        size = min(h, w)
        mask = self.create_ring_mask(size, outer_ratio, inner_ratio)

        # 如果图像不是正方形，裁剪遮罩
        if h != w:
            mask = mask[:h, :w]

        if len(image.shape) == 3:
            return cv2.bitwise_and(image, image, mask=mask)
        else:
            return cv2.bitwise_and(image, image, mask=mask)

    # ==================== 图像转换 ====================

    def to_grayscale(self, image: np.ndarray) -> np.ndarray:
        """转换为灰度图"""
        if len(image.shape) == 2:
            return image
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def to_hsv(self, image: np.ndarray) -> np.ndarray:
        """转换为 HSV 颜色空间"""
        return cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    def resize(self, image: np.ndarray, width: int, height: int,
               interpolation: int = cv2.INTER_LINEAR) -> np.ndarray:
        """缩放图像"""
        return cv2.resize(image, (width, height), interpolation=interpolation)

    def gaussian_blur(self, image: np.ndarray, ksize: int = 5) -> np.ndarray:
        """高斯模糊"""
        return cv2.GaussianBlur(image, (ksize, ksize), 0)

    # ==================== 预处理流水线 ====================

    def preprocess_minimap(self, minimap: np.ndarray,
                           use_clahe: bool = True,
                           use_ring_mask: bool = True,
                           outer_ratio: float = 0.95,
                           inner_ratio: float = 0.0,
                           blur: bool = False) -> np.ndarray:
        """
        小地图预处理流水线

        完整的小地图预处理: 灰度 -> CLAHE -> 圆环遮罩 -> (可选模糊)

        Args:
            minimap: 原始小地图图像 (BGR)
            use_clahe: 是否使用 CLAHE 增强
            use_ring_mask: 是否使用圆环遮罩
            outer_ratio: 外圆比例
            inner_ratio: 内圆比例
            blur: 是否高斯模糊去噪

        Returns:
            预处理后的灰度图像
        """
        result = minimap.copy()

        # Step 1: 灰度
        result = self.to_grayscale(result)

        # Step 2: CLAHE 增强
        if use_clahe:
            result = self.apply_clahe(result)

        # Step 3: 圆环遮罩
        if use_ring_mask:
            result = self.apply_ring_mask(result, outer_ratio, inner_ratio)

        # Step 4: 可选高斯模糊
        if blur:
            result = self.gaussian_blur(result, 3)

        return result

    def preprocess_map_region(self, region: np.ndarray,
                              use_clahe: bool = True) -> np.ndarray:
        """
        世界地图区域预处理

        Args:
            region: 世界地图区域 (BGR)
            use_clahe: 是否使用 CLAHE

        Returns:
            预处理后的灰度图像
        """
        result = self.to_grayscale(region)
        if use_clahe:
            result = self.apply_clahe(result)
        return result
