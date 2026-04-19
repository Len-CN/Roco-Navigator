"""
模板匹配器

使用 OpenCV 模板匹配进行小地图可见性检测等场景。
支持可选的 GPU (CUDA) 加速。
"""

import logging
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

from ..utils.gpu_utils import get_gpu_manager

logger = logging.getLogger(__name__)


@dataclass
class TemplateMatchResult:
    """模板匹配结果"""
    found: bool
    location: Optional[Tuple[int, int]] = None  # (x, y) 最佳匹配位置
    confidence: float = 0.0
    all_locations: Optional[List[Tuple[int, int]]] = None


class TemplateMatcher:
    """
    模板匹配器

    用于:
    - 小地图可见性检测 (检测边框特征)
    - 特定 UI 元素检测
    - 图标识别
    """

    def __init__(self, use_gpu: bool = False):
        self._gpu_manager = get_gpu_manager()
        self._use_gpu = False  # Default to False

        if use_gpu and self._gpu_manager.check_gpu_available():
            if self._gpu_manager.enable_gpu():
                self._use_gpu = True
                logger.info("TemplateMatcher: GPU acceleration enabled")
            else:
                logger.info("TemplateMatcher: GPU not usable by OpenCV, CPU mode")
        else:
            logger.info("TemplateMatcher: CPU mode")

    def match_template(self, image: np.ndarray,
                       template: np.ndarray,
                       method: int = cv2.TM_CCOEFF_NORMED,
                       threshold: float = 0.8
                       ) -> TemplateMatchResult:
        """
        单模板匹配

        Args:
            image: 源图像
            template: 模板图像
            method: 匹配方法
            threshold: 匹配阈值

        Returns:
            TemplateMatchResult
        """
        if image is None or template is None:
            return TemplateMatchResult(found=False)

        # 确保图像类型一致
        if len(image.shape) == 3 and len(template.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 2 and len(template.shape) == 3:
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        # 模板不能大于图像
        if (template.shape[0] > image.shape[0] or
                template.shape[1] > image.shape[1]):
            return TemplateMatchResult(found=False)

        # 执行匹配
        if self._use_gpu and self._gpu_manager.is_enabled():
            result = self._match_gpu(image, template, method)
        else:
            result = self._match_cpu(image, template, method)

        if result is None:
            return TemplateMatchResult(found=False)

        # 找最佳匹配
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 根据方法选择最优值
        if method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
            best_loc = min_loc
            confidence = 1.0 - min_val
        else:
            best_loc = max_loc
            confidence = max_val

        found = confidence >= threshold

        return TemplateMatchResult(
            found=found,
            location=best_loc if found else None,
            confidence=confidence
        )

    def match_template_multi(self, image: np.ndarray,
                             template: np.ndarray,
                             method: int = cv2.TM_CCOEFF_NORMED,
                             threshold: float = 0.8
                             ) -> TemplateMatchResult:
        """
        多目标模板匹配 (查找所有匹配位置)

        Args:
            image: 源图像
            template: 模板图像
            method: 匹配方法
            threshold: 匹配阈值

        Returns:
            TemplateMatchResult (包含 all_locations)
        """
        if image is None or template is None:
            return TemplateMatchResult(found=False)

        if len(image.shape) == 3 and len(template.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        if (template.shape[0] > image.shape[0] or
                template.shape[1] > image.shape[1]):
            return TemplateMatchResult(found=False)

        result = self._match_cpu(image, template, method)
        if result is None:
            return TemplateMatchResult(found=False)

        # 找所有超过阈值的匹配
        locations = np.where(result >= threshold)
        points = list(zip(locations[1].tolist(), locations[0].tolist()))

        if not points:
            return TemplateMatchResult(found=False, confidence=0.0)

        # NMS 去重 (简单距离过滤)
        filtered = self._nms_points(points, min_distance=20)

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        return TemplateMatchResult(
            found=True,
            location=max_loc,
            confidence=max_val,
            all_locations=filtered
        )

    def _match_cpu(self, image: np.ndarray, template: np.ndarray,
                   method: int) -> Optional[np.ndarray]:
        """CPU 模板匹配"""
        try:
            return cv2.matchTemplate(image, template, method)
        except cv2.error as e:
            logger.error("Template matching failed: %s", e)
            return None

    def _match_gpu(self, image: np.ndarray, template: np.ndarray,
                   method: int) -> Optional[np.ndarray]:
        """GPU 加速模板匹配"""
        try:
            gpu_image = cv2.cuda_GpuMat()
            gpu_template = cv2.cuda_GpuMat()
            gpu_image.upload(image)
            gpu_template.upload(template)

            matcher = cv2.cuda.createTemplateMatching(image.dtype, method)
            gpu_result = matcher.match(gpu_image, gpu_template)

            return gpu_result.download()
        except Exception as e:
            logger.warning("GPU template matching failed, falling back to CPU: %s", e)
            return self._match_cpu(image, template, method)

    @staticmethod
    def _nms_points(points: List[Tuple[int, int]],
                    min_distance: int = 20) -> List[Tuple[int, int]]:
        """简单的非极大值抑制 (距离过滤)"""
        if not points:
            return []

        filtered = [points[0]]
        for pt in points[1:]:
            too_close = False
            for existing in filtered:
                dist = ((pt[0] - existing[0]) ** 2 + (pt[1] - existing[1]) ** 2) ** 0.5
                if dist < min_distance:
                    too_close = True
                    break
            if not too_close:
                filtered.append(pt)

        return filtered
