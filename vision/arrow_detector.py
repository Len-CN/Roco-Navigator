"""
玩家朝向检测

从小地图中心区域提取黄色箭头，通过凸包尖端分析计算朝向角度。
"""

import logging
import math
from typing import Optional, Tuple, List
from collections import deque

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ArrowDetector:
    """检测小地图中心的黄色箭头朝向"""

    def __init__(self):
        # Yellow arrow HSV range (收紧范围，减少地图黄色元素误检)
        self._lower_yellow = np.array([15, 100, 180])
        self._upper_yellow = np.array([35, 255, 255])

        # Minimum pixel count to consider a valid arrow detection
        self._min_arrow_pixels = 15

        # Angle smoothing buffer (5帧平衡稳定性和响应速度)
        self._angle_history: deque = deque(maxlen=5)
        self._last_valid_angle: Optional[float] = None

        # 裁剪区域圆形遮罩缓存
        self._crop_mask_cache: dict = {}

    def detect_direction(self, minimap_bgr: np.ndarray) -> Optional[float]:
        """
        Detect player arrow direction from minimap image.

        Uses convex hull tip detection for robust direction finding,
        with angle smoothing to reduce jitter.

        Args:
            minimap_bgr: Full minimap BGR image

        Returns:
            Direction in degrees (0=north/up, 90=east/right, 180=south, 270=west)
            or None if detection fails.
        """
        h, w = minimap_bgr.shape[:2]

        # 缩小裁剪区域 (//8)，聚焦箭头本体，减少地图元素干扰
        size = min(h, w) // 8
        cy, cx = h // 2, w // 2
        y1 = max(0, cy - size)
        y2 = min(h, cy + size)
        x1 = max(0, cx - size)
        x2 = min(w, cx + size)
        center_crop = minimap_bgr[y1:y2, x1:x2]

        # 预模糊降噪，减少 HSV 阈值化后的碎片轮廓
        blurred = cv2.GaussianBlur(center_crop, (5, 5), 0)

        # Convert to HSV and threshold for yellow
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._lower_yellow, self._upper_yellow)

        # 圆形遮罩：抑制裁剪区域边角的地图元素
        crop_h, crop_w = mask.shape[:2]
        crop_size = min(crop_h, crop_w)
        if crop_size not in self._crop_mask_cache:
            cmask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.circle(cmask, (crop_w // 2, crop_h // 2), crop_size // 2, 255, -1)
            self._crop_mask_cache[crop_size] = cmask
        circle_mask = self._crop_mask_cache[crop_size]
        mask = cv2.bitwise_and(mask, circle_mask)

        # 自适应饱和度：地图偏黄时逐步收紧饱和度下限，隔离高饱和箭头
        circle_pixels = max(1, cv2.countNonZero(circle_mask))
        yellow_ratio = cv2.countNonZero(mask) / circle_pixels
        if yellow_ratio > 0.25:
            for sat_boost in (40, 80, 120):
                tighter = self._lower_yellow.copy()
                tighter[1] = min(255, self._lower_yellow[1] + sat_boost)
                mask = cv2.inRange(hsv, tighter, self._upper_yellow)
                mask = cv2.bitwise_and(mask, circle_mask)
                if cv2.countNonZero(mask) / circle_pixels < 0.25:
                    break

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Check minimum pixel count
        yellow_pixels = cv2.countNonZero(mask)
        if yellow_pixels < self._min_arrow_pixels:
            return self._last_valid_angle

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return self._last_valid_angle

        # Get the largest contour (should be the arrow)
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < self._min_arrow_pixels:
            return self._last_valid_angle

        # 轮廓形状验证：面积不应超过裁剪区的 50%（否则是大面积黄色误检）
        crop_area = (y2 - y1) * (x2 - x1)
        if area > crop_area * 0.5:
            logger.debug("Arrow rejected: contour area %d > 50%% of crop %d", area, crop_area)
            return self._last_valid_angle

        # 最小外接矩形宽高比检查：箭头应有一定长宽比
        rect = cv2.minAreaRect(largest)
        rw, rh = rect[1]
        if rw > 0 and rh > 0:
            aspect = max(rw, rh) / min(rw, rh)
            if aspect < 1.2:
                # 太接近正方形/圆形，不像箭头
                logger.debug("Arrow rejected: aspect ratio %.2f < 1.2", aspect)
                return self._last_valid_angle

        # Find arrow tip using convex hull defect analysis
        angle = self._find_arrow_direction(largest)
        if angle is None:
            return self._last_valid_angle

        # Apply smoothing
        return self._smooth_angle(angle)

    def _find_arrow_direction(self, contour: np.ndarray) -> Optional[float]:
        """
        Find arrow direction using farthest-convex-hull-vertex method.

        箭头的质心偏向底部（像素密集区），尖端是距质心最远的凸包顶点。
        比"最锐角"方法更鲁棒，不依赖精确的角度计算。
        """
        pts = contour.reshape(-1, 2).astype(np.float32)
        if len(pts) < 5:
            return self._pca_fallback(pts)

        # 用矩阵计算精确质心
        M = cv2.moments(contour)
        if M["m00"] < 1:
            return self._pca_fallback(pts)
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

        # 凸包去噪
        hull = cv2.convexHull(contour, returnPoints=True)
        if hull is None or len(hull) < 3:
            return self._pca_fallback(pts)

        hull_pts = hull.reshape(-1, 2).astype(np.float32)

        # 找距质心最远的凸包顶点 → 箭头尖端
        dx = hull_pts[:, 0] - cx
        dy = hull_pts[:, 1] - cy
        dists_sq = dx * dx + dy * dy
        tip_idx = int(np.argmax(dists_sq))
        tip = hull_pts[tip_idx]

        dx_tip = tip[0] - cx
        dy_tip = tip[1] - cy

        if abs(dx_tip) < 0.5 and abs(dy_tip) < 0.5:
            return self._pca_fallback(pts)

        # Convert to compass bearing (0=north/up, clockwise)
        compass = (math.degrees(math.atan2(dx_tip, -dy_tip))) % 360
        return compass

    def _pca_fallback(self, pts: np.ndarray) -> Optional[float]:
        """PCA-based direction as fallback, with centroid-to-farthest-point disambiguation."""
        if len(pts) < 3:
            return None

        mean = np.mean(pts, axis=0)
        centered = pts - mean
        cov = np.cov(centered.T)
        if cov.shape != (2, 2):
            return None

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        principal = eigenvectors[:, np.argmax(eigenvalues)]

        # Disambiguate using farthest point from centroid along principal axis
        projections = centered @ principal
        # Use the direction toward the farthest projected point
        if abs(np.max(projections)) >= abs(np.min(projections)):
            direction = principal
        else:
            direction = -principal

        dx, dy = direction[0], direction[1]
        compass = (math.degrees(math.atan2(dx, -dy))) % 360
        return compass

    def _smooth_angle(self, raw_angle: float) -> float:
        """
        Smooth angle using exponential-weighted circular mean.
        Filter out large jumps (> 120 degrees).
        """
        if self._last_valid_angle is not None:
            diff = ((raw_angle - self._last_valid_angle + 180) % 360) - 180
            if abs(diff) > 120:
                # 大跳变 — 检测错误，沿用上次值
                return self._last_valid_angle

        self._angle_history.append(raw_angle)
        self._last_valid_angle = raw_angle

        if len(self._angle_history) < 2:
            return raw_angle

        # 指数权重圆周均值 (最新帧权重最大)
        sin_sum = 0.0
        cos_sum = 0.0
        weight_sum = 0.0
        n = len(self._angle_history)
        for i, a in enumerate(self._angle_history):
            w = 2.0 ** i  # 指数权重: 1, 2, 4, 8, 16
            sin_sum += w * math.sin(math.radians(a))
            cos_sum += w * math.cos(math.radians(a))
            weight_sum += w

        avg_angle = math.degrees(math.atan2(sin_sum / weight_sum,
                                             cos_sum / weight_sum)) % 360
        self._last_valid_angle = avg_angle
        return avg_angle

    def set_hsv_range(self, lower: Tuple[int, int, int], upper: Tuple[int, int, int]):
        """Adjust HSV range for arrow detection"""
        self._lower_yellow = np.array(lower)
        self._upper_yellow = np.array(upper)

    def reset(self):
        """Reset angle history"""
        self._angle_history.clear()
        self._last_valid_angle = None
