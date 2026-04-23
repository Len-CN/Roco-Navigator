"""
DISK + LightGlue 特征匹配器

使用 Kornia 的 DISK 特征提取器和 LightGlue 匹配器，替代 LoFTR 作为深度学习主匹配方案。
支持预计算（分块提取 + 网格空间索引）和磁盘缓存。
需要安装 torch 和 kornia：通过设置中的"功能管理器"安装。
"""

import hashlib
import logging
import math
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import flag
_LIGHTGLUE_CHECKED = False
_LIGHTGLUE_AVAILABLE = False


def is_lightglue_available() -> bool:
    """Check if DISK + LightGlue dependencies (torch + kornia) are installed."""
    global _LIGHTGLUE_CHECKED, _LIGHTGLUE_AVAILABLE

    if not _LIGHTGLUE_CHECKED:
        _LIGHTGLUE_CHECKED = True
        try:
            import torch
            import kornia
            from kornia.feature import DISK, LightGlue
            _LIGHTGLUE_AVAILABLE = True
            logger.info(
                "LightGlue dependencies loaded (torch=%s, kornia=%s)",
                torch.__version__, kornia.__version__,
            )
        except (ImportError, OSError, RuntimeError) as e:
            logger.warning("LightGlue dependencies not available: %s", e)
            _LIGHTGLUE_AVAILABLE = False

    return _LIGHTGLUE_AVAILABLE


@dataclass
class LightGlueMatchResult:
    """LightGlue matching result"""
    success: bool
    position: Optional[Tuple[float, float]] = None
    confidence: float = 0.0
    num_matches: int = 0
    inliers: int = 0
    homography: Optional[np.ndarray] = None


class LightGlueMatcher:
    """
    DISK + LightGlue feature matcher using Kornia.

    Advantages over LoFTR:
    - Adaptive early stopping (fast on easy pairs, thorough on hard ones)
    - Better accuracy on outdoor/game-map scenes
    - Sparse matching with strong descriptors

    Advantages over SIFT:
    - Learned features, more robust to texture-less regions
    - Learned matcher replaces ratio test + RANSAC chain
    """

    GRID_CELL_SIZE = 256
    TILE_SIZE = 512
    TILE_OVERLAP = 64

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        min_matches: int = 8,
        ransac_threshold: float = 8.0,
        device: Optional[str] = None,
        cache_features: bool = True,
    ):
        if not is_lightglue_available():
            raise RuntimeError(
                "LightGlue requires torch and kornia. "
                "Install via Settings -> Feature Manager."
            )

        import torch
        from kornia.feature import DISK, LightGlue

        self._confidence_threshold = confidence_threshold
        self._min_matches = min_matches
        self._ransac_threshold = ransac_threshold
        self._cache_features = cache_features

        # Device selection: CUDA > DirectML > CPU
        self._device = self._select_device(device)

        # Models
        self._extractor = DISK.from_pretrained("depth").to(self._device).eval()
        self._matcher = LightGlue(features="disk").to(self._device).eval()

        # Pre-computed state
        self._map_keypoints: Optional[torch.Tensor] = None    # [N, 2]
        self._map_descriptors: Optional[torch.Tensor] = None   # [N, D]
        self._map_shape: Optional[Tuple[int, int]] = None
        self._grid_index: dict = {}
        self._map_precomputed = False

        logger.info(
            "LightGlueMatcher initialized (device=%s, cache=%s)",
            self._device, cache_features,
        )

    # ==================== Device selection ====================

    @staticmethod
    def _select_device(device: Optional[str]):
        import torch

        if device is not None:
            return torch.device(device)

        if torch.cuda.is_available():
            logger.info("LightGlue using CUDA GPU acceleration")
            return torch.device("cuda")

        try:
            import torch_directml
            if torch_directml.device_count() > 0:
                logger.info("LightGlue using DirectML GPU acceleration")
                return torch_directml.device(0)
        except ImportError:
            pass

        logger.warning("LightGlue falling back to CPU (no GPU detected)")
        return torch.device("cpu")

    # ==================== Image conversion ====================

    def _to_tensor(self, image: np.ndarray):
        """Convert grayscale/BGR numpy image to [1, 3, H, W] float tensor."""
        import torch

        if len(image.shape) == 3 and image.shape[2] == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif len(image.shape) == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            rgb = image

        # DISK expects [1, 3, H, W] float in [0, 1]
        tensor = torch.from_numpy(np.ascontiguousarray(rgb)).float() / 255.0
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)  # [H,W,3] -> [1,3,H,W]
        return tensor.to(self._device)

    # ==================== Tiled feature extraction ====================

    @staticmethod
    def _iter_tiles(image: np.ndarray, tile_size: int, overlap: int):
        """Yield (tile, (offset_x, offset_y)) over the image."""
        h, w = image.shape[:2]
        step = tile_size - overlap
        for y in range(0, h, step):
            for x in range(0, w, step):
                y2 = min(y + tile_size, h)
                x2 = min(x + tile_size, w)
                tile = image[y:y2, x:x2]
                if tile.shape[0] < 32 or tile.shape[1] < 32:
                    continue
                yield tile, (x, y)

    # ==================== Pre-computation ====================

    def precompute_map_features(self, map_gray: np.ndarray) -> int:
        """
        Pre-compute DISK features for the entire world map.

        Uses tiled extraction to handle large maps, and caches results
        to disk so subsequent startups are instant.

        Args:
            map_gray: Grayscale world map image

        Returns:
            Number of features extracted
        """
        import torch

        # Try loading from cache
        if self._cache_features:
            cache_path = self._get_cache_path(map_gray)
            if cache_path.exists():
                try:
                    data = np.load(str(cache_path))
                    self._map_keypoints = torch.from_numpy(data["keypoints"]).float()
                    self._map_descriptors = torch.from_numpy(data["descriptors"]).float()
                    self._map_shape = map_gray.shape[:2]
                    self._build_grid_index()
                    self._map_precomputed = True
                    logger.info(
                        "Loaded %d cached DISK features from %s",
                        len(self._map_keypoints), cache_path.name,
                    )
                    return len(self._map_keypoints)
                except Exception as e:
                    logger.warning("Failed to load feature cache: %s", e)

        logger.info(
            "Pre-computing DISK features for world map (%dx%d)...",
            map_gray.shape[1], map_gray.shape[0],
        )
        start_time = time.perf_counter()
        self._map_shape = map_gray.shape[:2]

        all_keypoints = []
        all_descriptors = []

        with torch.no_grad():
            for tile, (ox, oy) in self._iter_tiles(
                map_gray, self.TILE_SIZE, self.TILE_OVERLAP
            ):
                tensor = self._to_tensor(tile)
                feats = self._extractor(tensor)

                kps = feats[0].keypoints  # [K, 2]
                des = feats[0].descriptors  # [K, D]

                if kps is not None and len(kps) > 0:
                    # Convert tile-local coords to global
                    offset = torch.tensor(
                        [[ox, oy]], dtype=kps.dtype, device=kps.device
                    )
                    kps = kps + offset
                    all_keypoints.append(kps.cpu())
                    all_descriptors.append(des.cpu())

        if not all_keypoints:
            logger.warning("No DISK features found in world map!")
            self._map_precomputed = False
            return 0

        self._map_keypoints = torch.cat(all_keypoints, dim=0)
        self._map_descriptors = torch.cat(all_descriptors, dim=0)

        # De-duplicate overlapping region features
        self._deduplicate_features()

        # Build grid index
        self._build_grid_index()
        self._map_precomputed = True

        elapsed = time.perf_counter() - start_time
        logger.info(
            "Pre-computed %d DISK features in %.1fs (%d grid cells)",
            len(self._map_keypoints), elapsed, len(self._grid_index),
        )

        # Save to cache
        if self._cache_features:
            self._save_cache(map_gray)

        return len(self._map_keypoints)

    def _deduplicate_features(self, min_dist: float = 3.0):
        """Remove duplicate keypoints from tile overlaps."""
        import torch

        if self._map_keypoints is None or len(self._map_keypoints) == 0:
            return

        # Simple grid-based dedup
        seen = {}
        keep = []
        cell = min_dist
        for i, kp in enumerate(self._map_keypoints):
            gx = int(kp[0].item() / cell)
            gy = int(kp[1].item() / cell)
            key = (gx, gy)
            if key not in seen:
                seen[key] = i
                keep.append(i)

        if len(keep) < len(self._map_keypoints):
            logger.debug(
                "Dedup: %d -> %d features",
                len(self._map_keypoints), len(keep),
            )
            indices = torch.tensor(keep, dtype=torch.long)
            self._map_keypoints = self._map_keypoints[indices]
            self._map_descriptors = self._map_descriptors[indices]

    def _build_grid_index(self):
        """Build spatial grid index from pre-computed keypoints."""
        self._grid_index = defaultdict(list)
        cell = self.GRID_CELL_SIZE
        for i, kp in enumerate(self._map_keypoints):
            gx = int(kp[0].item()) // cell
            gy = int(kp[1].item()) // cell
            self._grid_index[(gx, gy)].append(i)

    def _get_features_in_radius(
        self, cx: float, cy: float, radius: float
    ):
        """Get pre-computed features within radius using grid index."""
        import torch

        cell = self.GRID_CELL_SIZE
        gx_min = max(0, int((cx - radius) // cell))
        gx_max = int((cx + radius) // cell)
        gy_min = max(0, int((cy - radius) // cell))
        gy_max = int((cy + radius) // cell)

        indices = []
        for gx in range(gx_min, gx_max + 1):
            for gy in range(gy_min, gy_max + 1):
                indices.extend(self._grid_index.get((gx, gy), []))

        if not indices:
            return None, None

        # Filter by circular radius
        radius_sq = radius * radius
        filtered = []
        for i in indices:
            kp = self._map_keypoints[i]
            dx = kp[0].item() - cx
            dy = kp[1].item() - cy
            if dx * dx + dy * dy <= radius_sq:
                filtered.append(i)

        if not filtered:
            return None, None

        idx = torch.tensor(filtered, dtype=torch.long)
        return self._map_keypoints[idx], self._map_descriptors[idx]

    # ==================== Feature cache ====================

    def _get_cache_path(self, map_gray: np.ndarray) -> Path:
        """Generate cache file path based on map image hash."""
        # Hash a sample of the image for speed
        sample = map_gray[::8, ::8].tobytes()
        h = hashlib.md5(sample).hexdigest()[:12]
        from ..utils.file_utils import get_data_dir
        cache_dir = Path(get_data_dir()) / "cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"disk_features_{h}.npz"

    def _save_cache(self, map_gray: np.ndarray):
        """Save pre-computed features to disk."""
        try:
            cache_path = self._get_cache_path(map_gray)
            np.savez(
                str(cache_path),
                keypoints=self._map_keypoints.numpy(),
                descriptors=self._map_descriptors.numpy(),
            )
            logger.info("Saved DISK feature cache: %s", cache_path.name)
        except Exception as e:
            logger.warning("Failed to save feature cache: %s", e)

    # ==================== Matching ====================

    def match(
        self,
        minimap: np.ndarray,
        map_region: np.ndarray,
        region_offset: Tuple[float, float] = (0, 0),
        minimap_mask: Optional[np.ndarray] = None,
    ) -> LightGlueMatchResult:
        """
        Match minimap against a map region using DISK + LightGlue.

        Args:
            minimap: Minimap image (BGR or grayscale)
            map_region: Map region to match against
            region_offset: Offset of map_region in world coordinates
            minimap_mask: Ring mask for minimap

        Returns:
            LightGlueMatchResult with position in world coordinates
        """
        import torch

        try:
            # Apply mask
            minimap_input = minimap
            if minimap_mask is not None:
                minimap_input = cv2.bitwise_and(minimap, minimap, mask=minimap_mask)

            # Extract features
            with torch.no_grad():
                feats0 = self._extractor(self._to_tensor(minimap_input))
                feats1 = self._extractor(self._to_tensor(map_region))

            if len(feats0[0].keypoints) < self._min_matches:
                return LightGlueMatchResult(success=False)

            # Match
            result = self._run_lightglue(
                feats0[0].keypoints, feats0[0].descriptors,
                feats1[0].keypoints, feats1[0].descriptors,
                minimap_input.shape[:2], map_region.shape[:2],
            )

            if not result.success:
                return result

            # Adjust position by region offset
            if result.position is not None:
                result.position = (
                    result.position[0] + region_offset[0],
                    result.position[1] + region_offset[1],
                )

            return result

        except Exception as e:
            logger.warning("LightGlue matching failed: %s", e)
            return LightGlueMatchResult(success=False)

    def match_precomputed(
        self,
        minimap_gray: np.ndarray,
        search_center: Optional[Tuple[float, float]] = None,
        search_radius: float = 500,
        minimap_mask: Optional[np.ndarray] = None,
    ) -> LightGlueMatchResult:
        """
        Match minimap against pre-computed map features.

        Args:
            minimap_gray: Preprocessed minimap image
            search_center: Optional center for local search
            search_radius: Search radius in pixels
            minimap_mask: Ring mask for minimap

        Returns:
            LightGlueMatchResult with absolute world coordinates
        """
        import torch

        if not self._map_precomputed:
            return LightGlueMatchResult(success=False)

        try:
            # Apply mask
            minimap_input = minimap_gray
            if minimap_mask is not None:
                minimap_input = cv2.bitwise_and(
                    minimap_gray, minimap_gray, mask=minimap_mask
                )

            # Extract minimap features
            with torch.no_grad():
                feats0 = self._extractor(self._to_tensor(minimap_input))

            kps0 = feats0[0].keypoints
            des0 = feats0[0].descriptors

            if kps0 is None or len(kps0) < self._min_matches:
                return LightGlueMatchResult(success=False)

            # Get map features
            if search_center is not None:
                map_kps, map_des = self._get_features_in_radius(
                    search_center[0], search_center[1], search_radius
                )
            else:
                map_kps = self._map_keypoints
                map_des = self._map_descriptors

            if map_kps is None or len(map_kps) < self._min_matches:
                return LightGlueMatchResult(success=False)

            # Move to device for matching
            map_kps = map_kps.to(self._device)
            map_des = map_des.to(self._device)

            return self._run_lightglue(
                kps0, des0,
                map_kps, map_des,
                minimap_input.shape[:2],
                self._map_shape,
            )

        except Exception as e:
            logger.warning("LightGlue precomputed matching failed: %s", e)
            return LightGlueMatchResult(success=False)

    def _run_lightglue(
        self,
        kps0, des0,
        kps1, des1,
        image_size0: Tuple[int, int],
        image_size1: Tuple[int, int],
    ) -> LightGlueMatchResult:
        """Run LightGlue matching and RANSAC homography."""
        import torch

        h0, w0 = image_size0
        h1, w1 = image_size1

        with torch.no_grad():
            input_dict = {
                "keypoints0": kps0.unsqueeze(0) if kps0.dim() == 2 else kps0,
                "keypoints1": kps1.unsqueeze(0) if kps1.dim() == 2 else kps1,
                "descriptors0": des0.unsqueeze(0) if des0.dim() == 2 else des0,
                "descriptors1": des1.unsqueeze(0) if des1.dim() == 2 else des1,
                "image_size0": torch.tensor([[h0, w0]], device=self._device),
                "image_size1": torch.tensor([[h1, w1]], device=self._device),
            }

            if self._device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    matches_dict = self._matcher(input_dict)
            else:
                matches_dict = self._matcher(input_dict)

        match_indices = matches_dict["matches"][0].cpu()  # [M, 2]
        match_scores = matches_dict["scores"][0].cpu()     # [M]

        # Filter by confidence
        mask = match_scores >= self._confidence_threshold
        match_indices = match_indices[mask]
        match_scores = match_scores[mask]

        if len(match_indices) < self._min_matches:
            return LightGlueMatchResult(
                success=False, num_matches=len(match_indices)
            )

        # Get matched point coordinates
        kps0_np = kps0.cpu().numpy() if kps0.dim() == 2 else kps0[0].cpu().numpy()
        kps1_np = kps1.cpu().numpy() if kps1.dim() == 2 else kps1[0].cpu().numpy()

        src_pts = kps0_np[match_indices[:, 0].numpy()].reshape(-1, 1, 2).astype(np.float32)
        dst_pts = kps1_np[match_indices[:, 1].numpy()].reshape(-1, 1, 2).astype(np.float32)

        # RANSAC homography
        H, inlier_mask = cv2.findHomography(
            src_pts, dst_pts, cv2.RANSAC, self._ransac_threshold
        )

        if H is None:
            return LightGlueMatchResult(
                success=False, num_matches=len(match_indices)
            )

        inliers = int(inlier_mask.sum())

        # Validate homography
        det = abs(H[0, 0] * H[1, 1] - H[0, 1] * H[1, 0])
        inlier_ratio = inliers / max(len(match_indices), 1)

        if det < 0.01 or det > 100:
            logger.debug("LightGlue homography rejected: det=%.4f", det)
            return LightGlueMatchResult(
                success=False, num_matches=len(match_indices), inliers=inliers
            )

        if inlier_ratio < 0.25:
            logger.debug("LightGlue homography rejected: inlier_ratio=%.2f", inlier_ratio)
            return LightGlueMatchResult(
                success=False, num_matches=len(match_indices), inliers=inliers
            )

        # Transform minimap center to world coordinates
        center = np.float32([[[w0 / 2, h0 / 2]]])
        world_pt = cv2.perspectiveTransform(center, H)
        world_x = float(world_pt[0][0][0])
        world_y = float(world_pt[0][0][1])

        # Map bounds check
        if self._map_shape is not None:
            margin = 50
            mh, mw = self._map_shape
            if world_x < -margin or world_x > mw + margin:
                return LightGlueMatchResult(success=False)
            if world_y < -margin or world_y > mh + margin:
                return LightGlueMatchResult(success=False)

        # Confidence
        avg_score = float(match_scores.mean()) if len(match_scores) > 0 else 0.0
        final_confidence = min(
            1.0,
            avg_score * inlier_ratio * math.sqrt(
                inliers / max(self._min_matches, 1)
            ),
        )

        return LightGlueMatchResult(
            success=True,
            position=(world_x, world_y),
            confidence=final_confidence,
            num_matches=len(match_indices),
            inliers=inliers,
            homography=H,
        )

    # ==================== Properties ====================

    @property
    def is_precomputed(self) -> bool:
        return self._map_precomputed

    @property
    def device(self) -> str:
        return str(self._device)
