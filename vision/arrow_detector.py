"""
玩家朝向检测

从小地图中心区域提取箭头，通过精确颜色匹配 + 凸包尖端分析计算朝向角度。
"""

import logging
import math
from typing import Optional, Tuple
from collections import deque

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ArrowDetector:
    """检测小地图中心的玩家箭头朝向"""

    def __init__(self):
        # 箭头的两种精确颜色 (BGR 格式)
        self._arrow_color1 = np.array([48, 183, 254], dtype=np.int16)   # RGB(254,183,48)
        self._arrow_color2 = np.array([26, 139, 231], dtype=np.int16)   # RGB(231,139,26)
        # 颜色容差 (L1 距离，三通道绝对差之和)
        self._color_tolerance = 80

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

        Args:
            minimap_bgr: Full minimap BGR image

        Returns:
            Direction in degrees (0=north/up, 90=east/right, 180=south, 270=west)
            or None if detection fails.
        """
        h, w = minimap_bgr.shape[:2]

        # 缩小裁剪区域 (//8)，聚焦箭头本体
        size = min(h, w) // 8
        cy, cx = h // 2, w // 2
        y1 = max(0, cy - size)
        y2 = min(h, cy + size)
        x1 = max(0, cx - size)
        x2 = min(w, cx + size)
        center_crop = minimap_bgr[y1:y2, x1:x2]

        # 预模糊降噪
        blurred = cv2.GaussianBlur(center_crop, (5, 5), 0)

        # 圆形遮罩
        crop_h, crop_w = blurred.shape[:2]
        crop_size = min(crop_h, crop_w)
        if crop_size not in self._crop_mask_cache:
            cmask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.circle(cmask, (crop_w // 2, crop_h // 2), crop_size // 2, 255, -1)
            self._crop_mask_cache[crop_size] = cmask
        circle_mask = self._crop_mask_cache[crop_size]

        # ── 精确颜色匹配：计算每个像素到两种箭头颜色的 L1 距离 ──
        pixels = blurred.astype(np.int16)
        dist1 = np.sum(np.abs(pixels - self._arrow_color1), axis=2)
        dist2 = np.sum(np.abs(pixels - self._arrow_color2), axis=2)
        # 取到两种颜色中较近的距离
        min_dist = np.minimum(dist1, dist2)
        # 容差内的像素 = 箭头
        mask = (min_dist <= self._color_tolerance).astype(np.uint8) * 255
        mask = cv2.bitwise_and(mask, circle_mask)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Check minimum pixel count
        if cv2.countNonZero(mask) < self._min_arrow_pixels:
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

        # 面积上限：不应超过裁剪区的 50%
        crop_area = (y2 - y1) * (x2 - x1)
        if area > crop_area * 0.5:
            return self._last_valid_angle

        # 宽高比检查：箭头有一定长宽比
        rect = cv2.minAreaRect(largest)
        rw, rh = rect[1]
        if rw > 0 and rh > 0:
            aspect = max(rw, rh) / min(rw, rh)
            if aspect < 1.2:
                return self._last_valid_angle

        # 凸包尖端法求方向
        angle = self._find_arrow_direction(largest)
        if angle is None:
            return self._last_valid_angle

        return self._smooth_angle(angle)

    def _find_arrow_direction(self, contour: np.ndarray) -> Optional[float]:
        """
        质心→最远凸包顶点 = 箭头尖端方向。

        箭头质心偏向底部（像素密集区），尖端是距质心最远的凸包顶点。
        """
        pts = contour.reshape(-1, 2).astype(np.float32)
        if len(pts) < 5:
            return self._pca_fallback(pts)

        M = cv2.moments(contour)
        if M["m00"] < 1:
            return self._pca_fallback(pts)
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

        hull = cv2.convexHull(contour, returnPoints=True)
        if hull is None or len(hull) < 3:
            return self._pca_fallback(pts)

        hull_pts = hull.reshape(-1, 2).astype(np.float32)
        dx = hull_pts[:, 0] - cx
        dy = hull_pts[:, 1] - cy
        dists_sq = dx * dx + dy * dy
        tip_idx = int(np.argmax(dists_sq))
        tip = hull_pts[tip_idx]

        dx_tip = tip[0] - cx
        dy_tip = tip[1] - cy
        if abs(dx_tip) < 0.5 and abs(dy_tip) < 0.5:
            return self._pca_fallback(pts)

        return (math.degrees(math.atan2(dx_tip, -dy_tip))) % 360

    def _pca_fallback(self, pts: np.ndarray) -> Optional[float]:
        """PCA 方向回退"""
        if len(pts) < 3:
            return None

        mean = np.mean(pts, axis=0)
        centered = pts - mean
        cov = np.cov(centered.T)
        if cov.shape != (2, 2):
            return None

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        principal = eigenvectors[:, np.argmax(eigenvalues)]

        projections = centered @ principal
        if abs(np.max(projections)) >= abs(np.min(projections)):
            direction = principal
        else:
            direction = -principal

        return (math.degrees(math.atan2(direction[0], -direction[1]))) % 360

    def _smooth_angle(self, raw_angle: float) -> float:
        """指数权重圆周均值平滑，过滤 >120° 大跳变"""
        if self._last_valid_angle is not None:
            diff = ((raw_angle - self._last_valid_angle + 180) % 360) - 180
            if abs(diff) > 120:
                return self._last_valid_angle

        self._angle_history.append(raw_angle)
        self._last_valid_angle = raw_angle

        if len(self._angle_history) < 2:
            return raw_angle

        sin_sum = 0.0
        cos_sum = 0.0
        weight_sum = 0.0
        for i, a in enumerate(self._angle_history):
            w = 2.0 ** i
            sin_sum += w * math.sin(math.radians(a))
            cos_sum += w * math.cos(math.radians(a))
            weight_sum += w

        avg_angle = math.degrees(math.atan2(sin_sum / weight_sum,
                                             cos_sum / weight_sum)) % 360
        self._last_valid_angle = avg_angle
        return avg_angle

    def set_arrow_colors(self, color1_rgb: Tuple[int, int, int],
                         color2_rgb: Tuple[int, int, int],
                         tolerance: int = 80):
        """调整箭头颜色 (RGB 格式)"""
        self._arrow_color1 = np.array([color1_rgb[2], color1_rgb[1], color1_rgb[0]], dtype=np.int16)
        self._arrow_color2 = np.array([color2_rgb[2], color2_rgb[1], color2_rgb[0]], dtype=np.int16)
        self._color_tolerance = tolerance

    def reset(self):
        """Reset angle history"""
        self._angle_history.clear()
        self._last_valid_angle = None
