"""
玩家朝向检测

从小地图中心区域提取箭头，通过精确颜色匹配 + 凸包尖端分析计算朝向角度。
裁剪区域、模糊核、最小像素数等参数按小地图尺寸自适应缩放，兼容不同分辨率。
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
        # 颜色容差 (L1 距离)
        self._color_tolerance = 80

        # 角度平滑缓冲
        self._angle_history: deque = deque(maxlen=5)
        self._last_valid_angle: Optional[float] = None

        # 圆形遮罩缓存
        self._crop_mask_cache: dict = {}

    def detect_direction(self, minimap_bgr: np.ndarray) -> Optional[float]:
        """
        Detect player arrow direction from minimap image.

        Args:
            minimap_bgr: Full minimap BGR image

        Returns:
            Direction in degrees (0=north, 90=east, 180=south, 270=west)
            or None if detection fails.
        """
        h, w = minimap_bgr.shape[:2]
        short = min(h, w)

        # 自适应裁剪：取中心 1/7 区域，聚焦箭头本体
        size = max(short // 7, 6)
        cy, cx = h // 2, w // 2
        y1 = max(0, cy - size)
        y2 = min(h, cy + size)
        x1 = max(0, cx - size)
        x2 = min(w, cx + size)
        center_crop = minimap_bgr[y1:y2, x1:x2]

        crop_h, crop_w = center_crop.shape[:2]
        crop_short = min(crop_h, crop_w)

        # 自适应高斯模糊（小地图小时用小核）
        ksize = max(3, (crop_short // 8) | 1)  # 奇数，最小 3
        blurred = cv2.GaussianBlur(center_crop, (ksize, ksize), 0)

        # 圆形遮罩
        mask_key = (crop_h, crop_w)
        if mask_key not in self._crop_mask_cache:
            cmask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.circle(cmask, (crop_w // 2, crop_h // 2), crop_short // 2, 255, -1)
            self._crop_mask_cache[mask_key] = cmask
        circle_mask = self._crop_mask_cache[mask_key]

        # 精确颜色匹配：L1 距离到两种箭头颜色
        pixels = blurred.astype(np.int16)
        dist1 = np.sum(np.abs(pixels - self._arrow_color1), axis=2)
        dist2 = np.sum(np.abs(pixels - self._arrow_color2), axis=2)
        min_dist = np.minimum(dist1, dist2)
        mask = (min_dist <= self._color_tolerance).astype(np.uint8) * 255
        mask = cv2.bitwise_and(mask, circle_mask)

        # 形态学清理（核大小自适应）
        morph_k = max(2, crop_short // 12)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_k, morph_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 最小像素数按裁剪面积比例
        crop_area = crop_h * crop_w
        min_pixels = max(8, int(crop_area * 0.01))

        if cv2.countNonZero(mask) < min_pixels:
            return self._last_valid_angle

        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return self._last_valid_angle

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < min_pixels:
            return self._last_valid_angle

        if area > crop_area * 0.5:
            return self._last_valid_angle

        # 宽高比检查
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
        取最远的 Top-3 顶点做加权平均，比单点更稳定。
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

        # 取距质心最远的 Top-N 顶点（N=min(3, hull点数)）
        n_top = min(3, len(hull_pts))
        top_indices = np.argsort(dists_sq)[-n_top:]

        # 用最远点的方向作为基准
        tip_idx = int(np.argmax(dists_sq))
        tip_angle = math.atan2(dx[tip_idx], -dy[tip_idx])

        # 将 Top-N 中方向与最远点接近的（<60°）做加权平均
        sin_sum = 0.0
        cos_sum = 0.0
        weight_sum = 0.0
        for idx in top_indices:
            a = math.atan2(dx[idx], -dy[idx])
            diff = abs(((a - tip_angle + math.pi) % (2 * math.pi)) - math.pi)
            if diff < math.radians(60):
                w = dists_sq[idx]  # 越远权重越大
                sin_sum += w * math.sin(a)
                cos_sum += w * math.cos(a)
                weight_sum += w

        if weight_sum < 1e-6:
            # 回退到单点
            return (math.degrees(tip_angle)) % 360

        avg_angle = math.atan2(sin_sum / weight_sum, cos_sum / weight_sum)
        return (math.degrees(avg_angle)) % 360

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
