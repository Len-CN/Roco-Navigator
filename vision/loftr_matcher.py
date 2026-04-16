"""
LoFTR (Detector-Free Local Feature Matching with Transformers) 匹配器

使用 Kornia 的 LoFTR 实现深度学习特征匹配，作为 SIFT 的替代/补充方案。
需要安装 torch 和 kornia：通过设置中的"依赖管理"安装。
"""

import logging
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
        """
        import torch
        
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Resize to dimensions divisible by 8 (avoid zero-padding which creates
        # black borders that produce spurious matches)
        h, w = gray.shape
        new_h = ((h + 7) // 8) * 8
        new_w = ((w + 7) // 8) * 8
        if new_h != h or new_w != w:
            gray = cv2.resize(gray, (new_w, new_h))

        # Convert to tensor
        tensor = torch.from_numpy(gray).float() / 255.0
        tensor = tensor.unsqueeze(0).unsqueeze(0)  # [1, 1, H, W]
        return tensor.to(self._device)

    def match(self, minimap: np.ndarray, map_region: np.ndarray,
              region_offset: Tuple[float, float] = (0, 0)) -> LoFTRMatchResult:
        """
        Match minimap against a map region using LoFTR.

        Args:
            minimap: Minimap image (BGR or grayscale)
            map_region: Map region to match against (BGR or grayscale)
            region_offset: Offset of the map_region in world coordinates

        Returns:
            LoFTRMatchResult with position in world coordinates
        """
        import torch
        
        try:
            # Preprocess images
            img0 = self._preprocess(minimap)
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

            avg_conf = float(confidence.mean()) if len(confidence) > 0 else 0.0

            return LoFTRMatchResult(
                success=True,
                position=(world_x, world_y),
                confidence=avg_conf,
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
