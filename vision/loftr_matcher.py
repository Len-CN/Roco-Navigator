"""
LoFTR (Detector-Free Local Feature Matching with Transformers) 匹配器

使用 Kornia 的 LoFTR 实现深度学习特征匹配，作为 SIFT 的替代/补充方案。
需要安装 torch 和 kornia：通过设置中的"依赖管理"安装。
"""

import logging
import math
import time
from typing import Optional, Tuple, List
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import flag - check availability only when needed
_LOFTR_CHECKED = False
_LOFTR_AVAILABLE = False
_LOFTR_IMPORT_ERROR = None


def is_loftr_available() -> bool:
    """Check if LoFTR dependencies are installed."""
    global _LOFTR_CHECKED, _LOFTR_AVAILABLE, _LOFTR_IMPORT_ERROR
    
    if not _LOFTR_CHECKED:
        _LOFTR_CHECKED = True
        try:
            import torch
            import kornia
            from kornia.feature import LoFTR as KorniaLoFTR
            _LOFTR_AVAILABLE = True
            logger.info("LoFTR dependencies loaded successfully (torch=%s, kornia=%s)", 
                        torch.__version__, kornia.__version__)
        except (ImportError, OSError, RuntimeError) as e:
            _LOFTR_IMPORT_ERROR = str(e)
            logger.warning("LoFTR dependencies not available: %s", e)
            _LOFTR_AVAILABLE = False
    
    return _LOFTR_AVAILABLE


@dataclass
class LoFTRMatchResult:
    """LoFTR matching result"""
    success: bool
    position: Optional[Tuple[float, float]] = None
    confidence: float = 0.0
    num_matches: int = 0
    inliers: int = 0
    homography: Optional[np.ndarray] = None


class LoFTRMatcher:
    """
    LoFTR feature matcher using Kornia.

    Advantages over SIFT:
    - Works well on textureless/repetitive regions (water, grass, desert)
    - More robust to scale/viewpoint changes
    - No handcrafted feature engineering

    Disadvantages:
    - Requires GPU for real-time performance
    - Higher memory usage (~1GB VRAM)
    - Requires torch + kornia installation
    """

    def __init__(self,
                 pretrained: str = "outdoor",
                 confidence_threshold: float = 0.55,
                 min_matches: int = 9,
                 ransac_threshold: float = 8.0,
                 device: Optional[str] = None):
        """
        Args:
            pretrained: LoFTR pretrained weights ("outdoor" or "indoor")
            confidence_threshold: Minimum match confidence to keep
            min_matches: Minimum number of matches for homography
            ransac_threshold: RANSAC reprojection threshold
            device: "cuda" or "cpu" (auto-detect if None)
        """
        if not is_loftr_available():
            raise RuntimeError(
                "LoFTR requires torch and kornia. "
                "Install via: pip install torch kornia"
            )

        # Import torch and kornia here (after availability check)
        import torch
        import kornia
        from kornia.feature import LoFTR as KorniaLoFTR

        self._confidence_threshold = confidence_threshold
        self._min_matches = min_matches
        self._ransac_threshold = ransac_threshold

        # Auto-detect device
        cuda_available = torch.cuda.is_available()
        logger.info("CUDA available: %s", cuda_available)
        if device is None:
            if cuda_available:
                self._device = torch.device("cuda")
                logger.info("LoFTR using CUDA GPU acceleration")
            else:
                self._device = torch.device("cpu")
                logger.warning(
                    "CUDA not available, LoFTR falling back to CPU. "
                    "Performance will be significantly slower. "
                    "Install CUDA-enabled PyTorch for GPU acceleration: "
                    "pip install torch --index-url https://download.pytorch.org/whl/cu121"
                )
        else:
            self._device = torch.device(device)

        # Initialize LoFTR model
        self._model = KorniaLoFTR(pretrained=pretrained)
        self._model = self._model.to(self._device)
        self._model.eval()

        logger.info("LoFTR initialized (device=%s, pretrained=%s, cuda_available=%s)",
                     self._device, pretrained, cuda_available)

    def _preprocess(self, image: np.ndarray):
        """Convert image to LoFTR input format.

        LoFTR expects grayscale float32 tensor [1, 1, H, W] with values in [0, 1].
        Dimensions must be divisible by 8.
        参考 Game-Map-Tracker: 向下取整裁剪（而非向上取整上采样），
        避免插值伪影和不必要的张量增大。
        """
        import torch

        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 向下取整到 8 的倍数（裁剪而非上采样）
        h, w = gray.shape
        new_h = h - (h % 8)
        new_w = w - (w % 8)
        if new_h != h or new_w != w:
            gray = gray[:new_h, :new_w]

        # Convert to tensor
        tensor = torch.from_numpy(gray.copy()).float() / 255.0
        tensor = tensor.unsqueeze(0).unsqueeze(0)  # [1, 1, H, W]
        return tensor.to(self._device)

    def match(self, minimap: np.ndarray, map_region: np.ndarray,
              region_offset: Tuple[float, float] = (0, 0),
              minimap_mask: Optional[np.ndarray] = None) -> LoFTRMatchResult:
        """
        Match minimap against a map region using LoFTR.

        Args:
            minimap: Minimap image (BGR or grayscale)
            map_region: Map region to match against (BGR or grayscale)
            region_offset: Offset of the map_region in world coordinates
            minimap_mask: 圆环遮罩，去除小地图中心玩家图标和边角 UI

        Returns:
            LoFTRMatchResult with position in world coordinates
        """
        import torch

        try:
            # 对小地图应用圆环遮罩（去除玩家图标和边角 UI 的干扰）
            minimap_input = minimap
            if minimap_mask is not None:
                if len(minimap.shape) == 3:
                    minimap_input = cv2.bitwise_and(minimap, minimap, mask=minimap_mask)
                else:
                    minimap_input = cv2.bitwise_and(minimap, minimap, mask=minimap_mask)

            # Preprocess images
            img0 = self._preprocess(minimap_input)
            img1 = self._preprocess(map_region)

            # Run LoFTR matching
            with torch.no_grad():
                if self._device.type == "cuda":
                    with torch.autocast(device_type="cuda", dtype=torch.float16):
                        input_dict = {"image0": img0, "image1": img1}
                        correspondences = self._model(input_dict)
                else:
                    input_dict = {"image0": img0, "image1": img1}
                    correspondences = self._model(input_dict)

            # Extract matches
            mkpts0 = correspondences["keypoints0"].cpu().numpy()  # minimap points
            mkpts1 = correspondences["keypoints1"].cpu().numpy()  # map region points
            confidence = correspondences["confidence"].cpu().numpy()

            # Filter by confidence
            mask = confidence >= self._confidence_threshold
            mkpts0 = mkpts0[mask]
            mkpts1 = mkpts1[mask]
            confidence = confidence[mask]

            if len(mkpts0) < self._min_matches:
                return LoFTRMatchResult(
                    success=False,
                    num_matches=len(mkpts0)
                )

            # RANSAC homography
            src_pts = mkpts0.reshape(-1, 1, 2).astype(np.float32)
            dst_pts = mkpts1.reshape(-1, 1, 2).astype(np.float32)

            H, inlier_mask = cv2.findHomography(
                src_pts, dst_pts, cv2.RANSAC, self._ransac_threshold
            )

            if H is None:
                return LoFTRMatchResult(
                    success=False,
                    num_matches=len(mkpts0)
                )

            inliers = int(inlier_mask.sum())

            # Transform minimap center to world coordinates
            h, w = minimap.shape[:2]
            center = np.float32([[[w / 2, h / 2]]])
            world_pt = cv2.perspectiveTransform(center, H)
            world_x = float(world_pt[0][0][0]) + region_offset[0]
            world_y = float(world_pt[0][0][1]) + region_offset[1]

            # Homography 质量验证
            det = abs(H[0, 0] * H[1, 1] - H[0, 1] * H[1, 0])
            inlier_ratio = inliers / max(len(mkpts0), 1)
            if det < 0.01 or det > 100:
                logger.debug("LoFTR homography rejected: det=%.4f", det)
                return LoFTRMatchResult(success=False, num_matches=len(mkpts0),
                                         inliers=inliers)
            if inlier_ratio < 0.25:
                logger.debug("LoFTR homography rejected: inlier_ratio=%.2f", inlier_ratio)
                return LoFTRMatchResult(success=False, num_matches=len(mkpts0),
                                         inliers=inliers)

            # 置信度：LoFTR confidence 均值 × 内点率 × 数量因子
            avg_conf = float(confidence.mean()) if len(confidence) > 0 else 0.0
            final_confidence = min(1.0, avg_conf * inlier_ratio * math.sqrt(
                inliers / max(self._min_matches, 1)))

            return LoFTRMatchResult(
                success=True,
                position=(world_x, world_y),
                confidence=final_confidence,
                num_matches=len(mkpts0),
                inliers=inliers,
                homography=H
            )

        except Exception as e:
            logger.warning("LoFTR matching failed: %s", e)
            return LoFTRMatchResult(success=False)

    @property
    def device(self) -> str:
        return str(self._device)
