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
        # Yellow arrow HSV range (wider range for different lighting)
        self._lower_yellow = np.array([10, 80, 150])
        self._upper_yellow = np.array([40, 255, 255])

        # Minimum pixel count to consider a valid arrow detection
        self._min_arrow_pixels = 15

        # Angle smoothing buffer (last N valid detections)
        self._angle_history: deque = deque(maxlen=5)
        self._last_valid_angle: Optional[float] = None

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

        # Extract smaller center region (15% of minimap) for speed + precision
        size = min(h, w) // 6
        cy, cx = h // 2, w // 2
        y1 = max(0, cy - size)
        y2 = min(h, cy + size)
        x1 = max(0, cx - size)
        x2 = min(w, cx + size)
        center_crop = minimap_bgr[y1:y2, x1:x2]

        # Convert to HSV and threshold for yellow
        hsv = cv2.cvtColor(center_crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._lower_yellow, self._upper_yellow)

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
        if cv2.contourArea(largest) < self._min_arrow_pixels:
            return self._last_valid_angle

        # Find arrow tip using convex hull defect analysis
        angle = self._find_arrow_direction(largest)
        if angle is None:
            return self._last_valid_angle

        # Apply smoothing
        return self._smooth_angle(angle)

    def _find_arrow_direction(self, contour: np.ndarray) -> Optional[float]:
        """
        Find arrow direction using convex hull tip detection.

        The arrow tip is the sharpest vertex of the convex hull
        (smallest angle between adjacent hull edges).
        """
        pts = contour.reshape(-1, 2).astype(np.float32)
        if len(pts) < 5:
            return self._pca_fallback(pts)

        # Compute centroid
        mean = np.mean(pts, axis=0)

        # Get convex hull indices (counter-clockwise)
        hull = cv2.convexHull(contour, returnPoints=False)
        if hull is None or len(hull) < 3:
            return self._pca_fallback(pts)

        hull_pts = contour[hull.flatten()].reshape(-1, 2).astype(np.float32)
        n = len(hull_pts)
        if n < 3:
            return self._pca_fallback(pts)

        # Find the sharpest angle (smallest interior angle = tip of arrow)
        min_angle = float('inf')
        tip_idx = 0

        for i in range(n):
            p_prev = hull_pts[(i - 1) % n]
            p_curr = hull_pts[i]
            p_next = hull_pts[(i + 1) % n]

            v1 = p_prev - p_curr
            v2 = p_next - p_curr

            len1 = np.linalg.norm(v1)
            len2 = np.linalg.norm(v2)
            if len1 < 1e-6 or len2 < 1e-6:
                continue

            cos_angle = np.dot(v1, v2) / (len1 * len2)
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle = math.acos(cos_angle)

            if angle < min_angle:
                min_angle = angle
                tip_idx = i

        # Arrow direction: from centroid to tip
        tip = hull_pts[tip_idx]
        dx = tip[0] - mean[0]
        dy = tip[1] - mean[1]

        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return self._pca_fallback(pts)

        # Convert to compass bearing (0=north/up, clockwise)
        compass = (math.degrees(math.atan2(dx, -dy))) % 360
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
        Smooth angle using weighted moving average.
        Filter out large jumps (> 90 degrees).
        """
        if self._last_valid_angle is not None:
            # Calculate shortest angular difference
            diff = ((raw_angle - self._last_valid_angle + 180) % 360) - 180
            if abs(diff) > 120:
                # Large jump — likely a detection error, use last valid
                return self._last_valid_angle

        self._angle_history.append(raw_angle)
        self._last_valid_angle = raw_angle

        if len(self._angle_history) < 2:
            return raw_angle

        # Weighted average (recent values weighted more)
        # Use circular mean to handle 0/360 wraparound
        sin_sum = 0.0
        cos_sum = 0.0
        weight_sum = 0.0
        for i, a in enumerate(self._angle_history):
            w = i + 1  # linear weight: older=1, newest=N
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
