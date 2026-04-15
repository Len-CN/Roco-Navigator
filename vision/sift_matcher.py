"""
SIFT 特征匹配器

使用 SIFT 特征点检测 + FLANN 匹配 + Lowe's ratio test + RANSAC
进行小地图与世界地图的特征匹配定位。

这是定位系统的核心算法模块。
"""

import logging
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
                 ratio_threshold: float = 0.7,
                 min_good_matches: int = 10,
                 ransac_reproj_threshold: float = 5.0):
        """
        初始化 SIFT 匹配器

        Args:
            n_features: 最大特征点数 (0=不限)
            contrast_threshold: 对比度阈值
            edge_threshold: 边缘阈值
            ratio_threshold: Lowe's ratio test 阈值
            min_good_matches: 最少有效匹配数
            ransac_reproj_threshold: RANSAC 重投影阈值
        """
        self._ratio_threshold = ratio_threshold
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
              region_offset: Tuple[int, int] = (0, 0)
              ) -> MatchResult:
        """
        将小地图与世界地图区域进行特征匹配

        Args:
            minimap: 小地图图像 (灰度)
            map_region: 世界地图搜索区域 (灰度)
            minimap_mask: 小地图遮罩 (可选)
            region_offset: 搜索区域在世界地图中的偏移 (x, y)

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

        # 2. KNN 匹配
        try:
            matches = self._flann.knnMatch(des1, des2, k=2)
        except cv2.error as e:
            logger.debug("FLANN matching failed: %s", e)
            return MatchResult(success=False)

        # 3. Lowe's ratio test
        good_matches = []
        for pair in matches:
            if len(pair) == 2:
                m, n = pair
                if m.distance < self._ratio_threshold * n.distance:
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

        # 加上区域偏移得到世界坐标
        world_x = float(world_point[0][0][0]) + region_offset[0]
        world_y = float(world_point[0][0][1]) + region_offset[1]

        # 7. 计算置信度
        confidence = min(1.0, inliers / max(self._min_good_matches, 1))

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
