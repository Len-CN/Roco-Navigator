"""
SIFT 特征匹配器

使用 SIFT 特征点检测 + FLANN 匹配 + Lowe's ratio test + RANSAC
进行小地图与世界地图的特征匹配定位。

这是定位系统的核心算法模块。
"""

import logging
import math
import time
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """匹配结果"""
    success: bool
    position: Optional[Tuple[float, float]] = None  # (x, y) in world coords
    homography: Optional[np.ndarray] = None
    good_matches: int = 0
    inliers: int = 0
    confidence: float = 0.0


class SIFTMatcher:
    """
    SIFT 特征匹配器

    使用 SIFT 算法检测关键点和描述子，
    通过 FLANN 进行快速近似最近邻匹配，
    Lowe's ratio test 过滤误匹配，
    RANSAC 计算单应性矩阵确定位置。
    """

    def __init__(self,
                 n_features: int = 0,
                 contrast_threshold: float = 0.04,
                 edge_threshold: float = 10,
                 ratio_threshold: float = 0.9,
                 local_ratio_threshold: float = 0.75,
                 min_good_matches: int = 5,
                 ransac_reproj_threshold: float = 8.0):
        """
        初始化 SIFT 匹配器

        Args:
            n_features: 最大特征点数 (0=不限)
            contrast_threshold: 对比度阈值
            edge_threshold: 边缘阈值
            ratio_threshold: Lowe's ratio test 阈值 (全局搜索)
            local_ratio_threshold: 局部搜索时更严格的 ratio 阈值
            min_good_matches: 最少有效匹配数
            ransac_reproj_threshold: RANSAC 重投影阈值
        """
        self._ratio_threshold = ratio_threshold
        self._local_ratio_threshold = local_ratio_threshold
        self._min_good_matches = min_good_matches
        self._ransac_threshold = ransac_reproj_threshold

        # 创建 SIFT 检测器
        self._sift = cv2.SIFT_create(
            nfeatures=n_features,
            contrastThreshold=contrast_threshold,
            edgeThreshold=edge_threshold
        )

        # 创建 FLANN 匹配器
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self._flann = cv2.FlannBasedMatcher(index_params, search_params)

        # 统计信息
        self._total_matches = 0
        self._successful_matches = 0

        # Pre-computed map features (populated by precompute_map_features)
        self._map_keypoints = None       # full list of cv2.KeyPoint
        self._map_descriptors = None     # full numpy array of descriptors
        self._map_precomputed = False

        # Spatial grid index for efficient local search
        self._grid_cell_size = 256       # pixels per grid cell
        self._grid_index = {}            # {(gx, gy): [indices into _map_keypoints]}
        self._map_shape = (0, 0)         # (height, width) of precomputed map

        # FLANN trained state for full precomputed set
        self._full_flann_trained = False

        logger.info(
            "SIFTMatcher initialized (ratio=%.2f, min_matches=%d, ransac=%.1f)",
            ratio_threshold, min_good_matches, ransac_reproj_threshold
        )

    def detect_and_compute(self, image: np.ndarray,
                           mask: Optional[np.ndarray] = None
                           ) -> Tuple[List, Optional[np.ndarray]]:
        """
        检测关键点并计算描述子

        Args:
            image: 灰度图像
            mask: 可选遮罩

        Returns:
            (keypoints, descriptors)
        """
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        keypoints, descriptors = self._sift.detectAndCompute(image, mask)
        return keypoints, descriptors

    def match(self, minimap: np.ndarray,
              map_region: np.ndarray,
              minimap_mask: Optional[np.ndarray] = None,
              region_offset: Tuple[int, int] = (0, 0),
              is_local: bool = False
              ) -> MatchResult:
        """
        将小地图与世界地图区域进行特征匹配

        Args:
            minimap: 小地图图像 (灰度)
            map_region: 世界地图搜索区域 (灰度)
            minimap_mask: 小地图遮罩 (可选)
            region_offset: 搜索区域在世界地图中的偏移 (x, y)
            is_local: 局部搜索模式 (使用更严格的 ratio 阈值)

        Returns:
            MatchResult: 匹配结果
        """
        self._total_matches += 1

        # 1. 提取特征点
        kp1, des1 = self.detect_and_compute(minimap, minimap_mask)
        kp2, des2 = self.detect_and_compute(map_region)

        if des1 is None or des2 is None:
            logger.debug("No descriptors found")
            return MatchResult(success=False)

        if len(des1) < 2 or len(des2) < 2:
            logger.debug("Not enough descriptors (minimap=%d, region=%d)",
                         len(des1) if des1 is not None else 0,
                         len(des2) if des2 is not None else 0)
            return MatchResult(success=False)

        # 2. KNN 匹配（小区域用 BFMatcher 更快，无需构建索引）
        try:
            if len(des2) < 2000:
                bf = cv2.BFMatcher(cv2.NORM_L2)
                matches = bf.knnMatch(des1, des2, k=2)
            else:
                matches = self._flann.knnMatch(des1, des2, k=2)
        except cv2.error as e:
            logger.debug("Matching failed: %s", e)
            return MatchResult(success=False)

        # 3. Lowe's ratio test（局部搜索用更严格的阈值）
        ratio = self._local_ratio_threshold if is_local else self._ratio_threshold
        good_matches = []
        for pair in matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < ratio * n.distance:
                    good_matches.append(m)

        if len(good_matches) < self._min_good_matches:
            logger.debug("Not enough good matches: %d < %d",
                         len(good_matches), self._min_good_matches)
            return MatchResult(success=False, good_matches=len(good_matches))

        # 4. 提取匹配点坐标
        src_pts = np.float32(
            [kp1[m.queryIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)
        dst_pts = np.float32(
            [kp2[m.trainIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)

        # 5. RANSAC 计算单应性矩阵
        H, mask = cv2.findHomography(
            src_pts, dst_pts,
            cv2.RANSAC,
            self._ransac_threshold
        )

        if H is None:
            logger.debug("Homography computation failed")
            return MatchResult(success=False, good_matches=len(good_matches))

        inliers = int(mask.sum()) if mask is not None else 0

        # 6. 计算小地图中心在世界地图中的位置
        h, w = minimap.shape[:2]
        center = np.float32([[[w / 2, h / 2]]])
        world_point = cv2.perspectiveTransform(center, H)

        world_x = float(world_point[0][0][0]) + region_offset[0]
        world_y = float(world_point[0][0][1]) + region_offset[1]

        # 7. Homography 质量验证
        map_h, map_w = map_region.shape[:2]
        if not self._validate_homography(H, inliers, len(good_matches),
                                         (map_h, map_w),
                                         world_x, world_y):
            return MatchResult(success=False, good_matches=len(good_matches),
                               inliers=inliers)

        # 8. 计算置信度（兼顾内点率和绝对数量）
        inlier_ratio = inliers / max(len(good_matches), 1)
        confidence = min(1.0, inlier_ratio * math.sqrt(
            inliers / max(self._min_good_matches, 1)))

        self._successful_matches += 1

        logger.debug(
            "Match success: pos=(%.1f, %.1f), good=%d, inliers=%d, conf=%.2f",
            world_x, world_y, len(good_matches), inliers, confidence
        )

        return MatchResult(
            success=True,
            position=(world_x, world_y),
            homography=H,
            good_matches=len(good_matches),
            inliers=inliers,
            confidence=confidence
        )

    # ==================== Pre-computed matching ====================

    def precompute_map_features(self, map_gray: np.ndarray) -> int:
        """
        Pre-compute SIFT features for the entire world map.
        Call once at startup after map is loaded.

        Args:
            map_gray: Grayscale world map image (already preprocessed)

        Returns:
            Number of features extracted
        """
        logger.info("Pre-computing SIFT features for world map (%dx%d)...",
                     map_gray.shape[1], map_gray.shape[0])

        start_time = time.perf_counter()
        self._map_shape = map_gray.shape[:2]

        # Detect and compute features on the full map
        self._map_keypoints, self._map_descriptors = self._sift.detectAndCompute(map_gray, None)

        if self._map_descriptors is None or len(self._map_descriptors) == 0:
            logger.warning("No features found in world map!")
            self._map_precomputed = False
            return 0

        # Build spatial grid index
        self._grid_index.clear()
        for i, kp in enumerate(self._map_keypoints):
            gx = int(kp.pt[0]) // self._grid_cell_size
            gy = int(kp.pt[1]) // self._grid_cell_size
            key = (gx, gy)
            if key not in self._grid_index:
                self._grid_index[key] = []
            self._grid_index[key].append(i)

        self._map_precomputed = True
        # Reset FLANN trained state so it rebuilds with new descriptors
        self._full_flann_trained = False

        elapsed = time.perf_counter() - start_time
        logger.info("Pre-computed %d SIFT features in %.1fs (%d grid cells)",
                     len(self._map_keypoints), elapsed, len(self._grid_index))
        return len(self._map_keypoints)

    def match_precomputed(self, minimap_gray: np.ndarray,
                          search_center: Optional[Tuple[float, float]] = None,
                          search_radius: float = 500,
                          minimap_mask: Optional[np.ndarray] = None) -> MatchResult:
        """
        Match minimap against pre-computed map features.

        If search_center is provided, only match against features within
        search_radius of that point (using spatial grid index).
        If search_center is None, match against ALL map features (global search).

        Args:
            minimap_gray: Preprocessed grayscale minimap image
            search_center: Optional (x, y) center for local search
            search_radius: Search radius in pixels (used with search_center)
            minimap_mask: Optional mask for minimap feature detection

        Returns:
            MatchResult with absolute world coordinates
        """
        if not self._map_precomputed:
            return MatchResult(success=False)

        self._total_matches += 1

        # Extract minimap features
        kp1, des1 = self.detect_and_compute(minimap_gray, minimap_mask)
        if des1 is None or len(des1) < 2:
            return MatchResult(success=False)

        # Get map features (filtered by search area or all)
        if search_center is not None:
            # Use spatial grid to get nearby features
            map_kp, map_des = self._get_features_in_radius(
                search_center[0], search_center[1], search_radius)
        else:
            # Global search: use all features
            map_kp = self._map_keypoints
            map_des = self._map_descriptors

        if map_des is None or len(map_des) < 2:
            return MatchResult(success=False)

        # FLANN match
        try:
            if search_center is not None and len(map_des) < len(self._map_descriptors):
                # For local subsets, BFMatcher is faster than building a new FLANN index
                bf = cv2.BFMatcher(cv2.NORM_L2)
                matches = bf.knnMatch(des1, map_des, k=2)
            else:
                # Use the persistent matcher for full set
                if not self._full_flann_trained:
                    self._flann.clear()
                    self._flann.add([self._map_descriptors])
                    self._flann.train()
                    self._full_flann_trained = True
                matches = self._flann.knnMatch(des1, k=2)
        except cv2.error as e:
            logger.debug("FLANN matching failed: %s", e)
            return MatchResult(success=False)

        # Lowe's ratio test（局部搜索用更严格的阈值）
        ratio = self._local_ratio_threshold if search_center is not None else self._ratio_threshold
        good_matches = []
        for pair in matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < ratio * n.distance:
                    good_matches.append(m)

        if len(good_matches) < self._min_good_matches:
            logger.debug("Not enough good matches: %d < %d",
                         len(good_matches), self._min_good_matches)
            return MatchResult(success=False, good_matches=len(good_matches))

        # Extract matched points (map features have absolute coords)
        src_pts = np.float32(
            [kp1[m.queryIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)
        dst_pts = np.float32(
            [map_kp[m.trainIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)

        # RANSAC homography
        H, mask = cv2.findHomography(
            src_pts, dst_pts,
            cv2.RANSAC,
            self._ransac_threshold
        )

        if H is None:
            logger.debug("Homography computation failed")
            return MatchResult(success=False, good_matches=len(good_matches))

        inliers = int(mask.sum()) if mask is not None else 0

        # Transform minimap center to absolute world coordinates
        h, w = minimap_gray.shape[:2]
        center = np.float32([[[w / 2, h / 2]]])
        world_point = cv2.perspectiveTransform(center, H)
        world_x = float(world_point[0][0][0])
        world_y = float(world_point[0][0][1])

        # Homography 质量验证
        if not self._validate_homography(H, inliers, len(good_matches),
                                         self._map_shape, world_x, world_y):
            return MatchResult(success=False, good_matches=len(good_matches),
                               inliers=inliers)

        # 置信度（兼顾内点率和绝对数量）
        inlier_ratio = inliers / max(len(good_matches), 1)
        confidence = min(1.0, inlier_ratio * math.sqrt(
            inliers / max(self._min_good_matches, 1)))

        self._successful_matches += 1

        logger.debug(
            "Precomputed match success: pos=(%.1f, %.1f), good=%d, inliers=%d, conf=%.2f",
            world_x, world_y, len(good_matches), inliers, confidence
        )

        return MatchResult(
            success=True,
            position=(world_x, world_y),
            homography=H,
            good_matches=len(good_matches),
            inliers=inliers,
            confidence=confidence
        )

    def _get_features_in_radius(self, cx: float, cy: float,
                                radius: float) -> Tuple[Optional[List], Optional[np.ndarray]]:
        """
        Get pre-computed features within a radius of a point, using grid index.

        Args:
            cx: Center x coordinate
            cy: Center y coordinate
            radius: Search radius in pixels

        Returns:
            (keypoints_subset, descriptors_subset) or (None, None)
        """
        cell = self._grid_cell_size
        gx_min = max(0, int((cx - radius) // cell))
        gx_max = int((cx + radius) // cell)
        gy_min = max(0, int((cy - radius) // cell))
        gy_max = int((cy + radius) // cell)

        indices = []
        for gx in range(gx_min, gx_max + 1):
            for gy in range(gy_min, gy_max + 1):
                cell_indices = self._grid_index.get((gx, gy), [])
                indices.extend(cell_indices)

        if not indices:
            return None, None

        # Filter by actual radius (circle, not square)
        radius_sq = radius * radius
        filtered = []
        for i in indices:
            kp = self._map_keypoints[i]
            dx = kp.pt[0] - cx
            dy = kp.pt[1] - cy
            if dx * dx + dy * dy <= radius_sq:
                filtered.append(i)

        if not filtered:
            return None, None

        kp_subset = [self._map_keypoints[i] for i in filtered]
        des_subset = np.take(self._map_descriptors, filtered, axis=0)

        return kp_subset, des_subset

    def _validate_homography(self, H: np.ndarray, inliers: int,
                              good_matches: int, map_shape: Tuple[int, int],
                              world_x: float, world_y: float) -> bool:
        """
        验证 Homography 矩阵质量，拒绝退化变换。

        检查:
        - 2x2 子矩阵行列式在合理范围内（排除奇异/极端缩放）
        - 内点率不过低（排除大量离群点产生的伪解）
        - 变换后坐标在地图范围内

        Args:
            H: 3x3 homography 矩阵
            inliers: RANSAC 内点数
            good_matches: ratio test 后的好匹配数
            map_shape: (height, width) 地图尺寸
            world_x: 变换后 x 坐标
            world_y: 变换后 y 坐标

        Returns:
            True 如果 homography 质量合格
        """
        # 行列式检查：小地图到世界地图的变换尺度应稳定，收紧范围
        det = abs(H[0, 0] * H[1, 1] - H[0, 1] * H[1, 0])
        if det < 0.1 or det > 10:
            logger.debug("Homography rejected: det=%.4f (out of [0.1, 10])", det)
            return False

        # 内点率检查
        inlier_ratio = inliers / max(good_matches, 1)
        if inlier_ratio < 0.25:
            logger.debug("Homography rejected: inlier_ratio=%.2f < 0.25", inlier_ratio)
            return False

        # 绝对内点数下限：至少 8 个内点才能可靠估计 homography
        if inliers < 8:
            logger.debug("Homography rejected: inliers=%d < 8", inliers)
            return False

        # 边界检查：变换后坐标应在地图范围内（允许少量溢出）
        map_h, map_w = map_shape
        margin = 50
        if (world_x < -margin or world_x > map_w + margin or
                world_y < -margin or world_y > map_h + margin):
            logger.debug("Homography rejected: pos=(%.1f, %.1f) out of map bounds (%d, %d)",
                         world_x, world_y, map_w, map_h)
            return False

        return True

    @property
    def is_precomputed(self) -> bool:
        """Whether map features have been pre-computed."""
        return self._map_precomputed

    def get_stats(self) -> dict:
        """获取匹配统计信息"""
        return {
            "total_matches": self._total_matches,
            "successful_matches": self._successful_matches,
            "success_rate": (
                self._successful_matches / max(1, self._total_matches)
            )
        }

    def reset_stats(self):
        """重置统计信息"""
        self._total_matches = 0
        self._successful_matches = 0
