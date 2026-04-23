"""
玩家朝向检测

使用灰度模板匹配 + NCC（归一化互相关）计算箭头朝向角度。
优先使用运行时自动校准模板（与当前分辨率精确匹配），
回退到预置参考模板（首帧即可用），最终回退到颜色+极坐标。

模板匹配的优势：
- 直接匹配完整像素图案（填充色 + 暗边框 + 色彩渐变），信息量远超二值形状
- 遮罩忽略背景像素，天然抗黄色/沙地等近色背景干扰
- 无 180° 歧义、无凸包/矩/极坐标等脆弱几何特征
"""

import logging
import math
import os
from typing import Optional, Tuple, List
from collections import deque

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_REF_TEMPLATE_FILE = "arrow_template.npz"
_REF_ANGLE = 0  # 参考模板中箭头的罗盘角（0=正北）


class ArrowDetector:
    """检测小地图中心的玩家箭头朝向"""

    def __init__(self):
        # 箭头颜色 (BGR) —— 颜色检测 / 自动校准用
        self._arrow_color1 = np.array([48, 183, 254], dtype=np.int16)
        self._arrow_color2 = np.array([26, 139, 231], dtype=np.int16)
        self._color_tolerance = 80

        # 模板匹配参数
        self._angle_step = 5
        self._n_angles = 360 // self._angle_step  # 72

        # 参考模板原始数据（未旋转，从文件加载）
        self._ref_gray: Optional[np.ndarray] = None
        self._ref_mask: Optional[np.ndarray] = None

        # 当前尺寸的预旋转模板 [(flat_indices, centered_vals, norm)]
        self._tmpl_data: list = []
        self._tmpl_crop_size: int = 0  # 模板当前适配的裁剪尺寸

        # 自动校准模板（运行时捕获，精确匹配当前分辨率）
        self._calib_gray: Optional[np.ndarray] = None
        self._calib_mask: Optional[np.ndarray] = None
        self._calib_data: list = []
        self._calib_crop_size: int = 0
        self._calibrated: bool = False

        # 角度平滑（3 帧减少延迟）
        self._angle_history: deque = deque(maxlen=3)
        self._last_valid_angle: Optional[float] = None

        self._load_reference()

    # ==================== 加载参考模板 ====================

    def _load_reference(self):
        """从 npz 文件加载参考模板原始数据。"""
        search_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'data_files',
                         _REF_TEMPLATE_FILE),
            os.path.join(os.path.dirname(__file__), '..', '..', 'data_files',
                         _REF_TEMPLATE_FILE),
            os.path.join('data_files', _REF_TEMPLATE_FILE),
        ]
        for path in search_paths:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                try:
                    data = np.load(path)
                    self._ref_gray = data['gray']
                    self._ref_mask = data['mask']
                    logger.info("Loaded arrow template from %s", path)
                    return
                except Exception as e:
                    logger.warning("Failed to load %s: %s", path, e)
        logger.warning("Arrow template not found, template matching disabled")

    # ==================== 按需构建旋转模板 ====================

    def _build_rotations(self, gray: np.ndarray, mask: np.ndarray
                         ) -> list:
        """从灰度图 + 遮罩构建 72 个预旋转模板。"""
        h, w = gray.shape
        center = (w / 2.0, h / 2.0)
        result: list = []
        for i in range(self._n_angles):
            deg = i * self._angle_step + _REF_ANGLE
            rot_mat = cv2.getRotationMatrix2D(center, -deg, 1.0)
            g_rot = cv2.warpAffine(gray, rot_mat, (w, h))
            m_rot = cv2.warpAffine(mask, rot_mat, (w, h),
                                   flags=cv2.INTER_NEAREST)
            indices = np.flatnonzero(m_rot > 0)
            if len(indices) < 20:
                result.append(None)
                continue
            t_vals = g_rot.flat[indices].astype(np.float32)
            t_c = t_vals - t_vals.mean()
            t_n = float(np.linalg.norm(t_c))
            if t_n < 1.0:
                result.append(None)
                continue
            result.append((indices, t_c, t_n))
        return result

    def _ensure_ref_templates(self, crop_size: int):
        """确保参考模板已缩放到当前裁剪尺寸并预旋转。"""
        if self._ref_gray is None:
            return
        if self._tmpl_crop_size == crop_size and self._tmpl_data:
            return
        ref_g = cv2.resize(self._ref_gray, (crop_size, crop_size))
        ref_m = cv2.resize(self._ref_mask, (crop_size, crop_size),
                           interpolation=cv2.INTER_NEAREST)
        self._tmpl_data = self._build_rotations(ref_g, ref_m)
        self._tmpl_crop_size = crop_size
        logger.info("Reference templates built at %dx%d",
                     crop_size, crop_size)

    # ==================== 主检测入口 ====================

    def detect_direction(self, minimap_bgr: np.ndarray) -> Optional[float]:
        h, w = minimap_bgr.shape[:2]
        short = min(h, w)
        size = max(short // 7, 6)
        cy, cx = h // 2, w // 2
        crop = minimap_bgr[max(0, cy - size):min(h, cy + size),
                           max(0, cx - size):min(w, cx + size)]
        crop_size = min(crop.shape[:2])

        # 1) 校准模板（精确分辨率 + 精确角度，最高优先级）
        if (self._calibrated and self._calib_data
                and self._calib_crop_size == crop_size):
            angle = self._ncc_match(crop, self._calib_data)
            if angle is not None:
                return self._smooth_angle(angle)

        # 2) 参考模板（从文件加载，按需缩放）
        self._ensure_ref_templates(crop_size)
        if self._tmpl_data:
            angle = self._ncc_match(crop, self._tmpl_data)
            if angle is not None:
                # 参考模板精度 <0.2°，用这个精确角度做校准
                if not self._calibrated:
                    self._try_calibrate(crop, angle)
                return self._smooth_angle(angle)

        # 3) 颜色 + 极坐标回退（不做校准，角度不够精确）
        angle = self._color_fallback(crop)
        if angle is not None:
            return self._smooth_angle(angle)

        return self._last_valid_angle

    # ==================== NCC 匹配 ====================

    def _ncc_match(self, crop_bgr: np.ndarray,
                   tmpl_list: list) -> Optional[float]:
        """NCC 模板匹配 + 抛物线插值。"""
        crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        ch, cw = crop_gray.shape

        # 尺寸适配：找到第一个有效模板条目获取目标尺寸
        first_entry = next((e for e in tmpl_list if e is not None), None)
        if first_entry is not None:
            expected_len = int(first_entry[0].max()) + 1
            actual_len = ch * cw
            if expected_len > actual_len:
                tmpl_side = int(math.isqrt(expected_len)) + 1
                crop_gray = cv2.resize(crop_gray, (tmpl_side, tmpl_side))

        crop_flat = crop_gray.astype(np.float32).ravel()
        flat_len = len(crop_flat)

        scores = np.full(self._n_angles, -2.0, dtype=np.float64)
        for i, entry in enumerate(tmpl_list):
            if entry is None:
                continue
            indices, t_centered, t_norm = entry
            if indices.max() >= flat_len:
                continue
            p = crop_flat[indices]
            p_c = p - p.mean()
            p_n = np.linalg.norm(p_c)
            if p_n < 1.0:
                continue
            scores[i] = float(np.dot(p_c, t_centered) / (p_n * t_norm))

        best_idx = int(np.argmax(scores))
        if scores[best_idx] < 0.5:
            return None

        # 抛物线插值
        prev_i = (best_idx - 1) % self._n_angles
        next_i = (best_idx + 1) % self._n_angles
        s_p, s_b, s_n = scores[prev_i], scores[best_idx], scores[next_i]
        denom = s_p - 2.0 * s_b + s_n
        offset = 0.0
        if abs(denom) > 1e-8:
            offset = 0.5 * (s_p - s_n) / denom
            offset = max(-0.5, min(0.5, offset))

        return float(((best_idx + offset) * self._angle_step) % 360)

    # ==================== 自动校准 ====================

    def _try_calibrate(self, crop_bgr: np.ndarray,
                       initial_angle: float):
        """从当前帧自动校准模板（精确匹配分辨率）。"""
        crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        ch, cw = crop_gray.shape
        crop_size = min(ch, cw)

        # 用颜色检测得到箭头遮罩
        mask = self._detect_arrow_mask(crop_bgr)
        if mask is None:
            return
        n_pixels = cv2.countNonZero(mask)
        if n_pixels < 50 or n_pixels > 400:
            return

        # 将箭头旋转到正北（canonical 0°）
        center = (cw / 2.0, ch / 2.0)
        rot_mat = cv2.getRotationMatrix2D(center, initial_angle, 1.0)
        calib_g = cv2.warpAffine(crop_gray, rot_mat, (cw, ch))
        calib_m = cv2.warpAffine(mask, rot_mat, (cw, ch),
                                 flags=cv2.INTER_NEAREST)

        self._calib_gray = calib_g
        self._calib_mask = calib_m
        self._calib_data = self._build_rotations(calib_g, calib_m)
        self._calib_crop_size = crop_size
        self._calibrated = True
        logger.info("Arrow template auto-calibrated at %dx%d (ref_angle=%.1f)",
                     crop_size, crop_size, initial_angle)

    def _detect_arrow_mask(self, crop_bgr: np.ndarray
                           ) -> Optional[np.ndarray]:
        """颜色检测 + 背景自适应过滤得到箭头掩码。"""
        ch, cw = crop_bgr.shape[:2]
        cs = min(ch, cw)

        ksize = max(3, (cs // 8) | 1)
        blurred = cv2.GaussianBlur(crop_bgr, (ksize, ksize), 0)

        # 圆形遮罩
        cmask = np.zeros((ch, cw), dtype=np.uint8)
        cv2.circle(cmask, (cw // 2, ch // 2), cs // 2, 255, -1)

        # 颜色匹配
        px = blurred.astype(np.int16)
        d1 = np.sum(np.abs(px - self._arrow_color1), axis=2)
        d2 = np.sum(np.abs(px - self._arrow_color2), axis=2)
        color_close = np.minimum(d1, d2) <= self._color_tolerance

        # 背景自适应：外圈中位数颜色，排除与背景太近的像素
        inner = np.zeros_like(cmask)
        cv2.circle(inner, (cw // 2, ch // 2), cs // 3, 255, -1)
        outer_ring = cv2.bitwise_and(cmask, cv2.bitwise_not(inner))
        bg_pixels = blurred[outer_ring > 0].reshape(-1, 3)
        if len(bg_pixels) > 10:
            bg_color = np.median(bg_pixels, axis=0).astype(np.int16)
            dist_bg = np.sum(np.abs(px - bg_color), axis=2)
            mask = (color_close & (dist_bg > 50)).astype(np.uint8) * 255
        else:
            mask = color_close.astype(np.uint8) * 255

        mask = cv2.bitwise_and(mask, cmask)

        mk = max(2, cs // 12)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (mk, mk))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 只保留最大轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < max(8, int(ch * cw * 0.005)):
            return None
        clean = np.zeros_like(mask)
        cv2.drawContours(clean, [largest], -1, 255, cv2.FILLED)
        return clean

    # ==================== 颜色回退 ====================

    def _color_fallback(self, crop_bgr: np.ndarray) -> Optional[float]:
        """颜色检测 + 背景过滤 + 极坐标 reach + 抛物线插值。"""
        mask = self._detect_arrow_mask(crop_bgr)
        if mask is None:
            return None
        ch, cw = mask.shape

        min_px = max(8, int(ch * cw * 0.005))
        if cv2.countNonZero(mask) < min_px:
            return None

        # _detect_arrow_mask 已返回单轮廓填充遮罩，直接计算矩
        M = cv2.moments(mask, binaryImage=True)
        if M["m00"] < 1:
            return None
        mcx = M["m10"] / M["m00"]
        mcy = M["m01"] / M["m00"]

        cs = min(ch, cw)
        max_r = cs // 2
        if max_r < 4:
            return None

        polar = cv2.warpPolar(
            mask, (max_r, 360),
            (float(mcx), float(mcy)), float(max_r),
            cv2.WARP_POLAR_LINEAR
        )
        col_idx = np.arange(max_r, dtype=np.float32)
        reach = np.maximum(
            np.max(np.where(polar > 0, col_idx[np.newaxis, :], -1.0),
                   axis=1),
            0.0
        ).astype(np.float32)

        if reach.max() < 2:
            return None

        win = 15
        smoothed = np.convolve(
            np.tile(reach, 3), np.ones(win, dtype=np.float32) / win,
            mode='same'
        )[360:720]

        peak_idx = int(np.argmax(smoothed))

        # 抛物线插值精细化
        prev_i = (peak_idx - 1) % 360
        next_i = (peak_idx + 1) % 360
        s_p, s_b, s_n = smoothed[prev_i], smoothed[peak_idx], smoothed[next_i]
        denom = s_p - 2.0 * s_b + s_n
        offset = 0.0
        if abs(denom) > 1e-8:
            offset = 0.5 * (s_p - s_n) / denom
            offset = max(-0.5, min(0.5, offset))

        compass = ((peak_idx + offset) + 90) % 360
        return float(compass)

    # ==================== 平滑 ====================

    def _smooth_angle(self, raw_angle: float) -> float:
        """
        抗抖动平滑：大变化立即响应，小抖动平滑过滤。

        游戏中玩家可以瞬间转向，不过滤跳变。
        仅对连续帧间的小幅抖动做指数加权平滑。
        """
        if self._last_valid_angle is not None:
            diff = abs(((raw_angle - self._last_valid_angle + 180) % 360)
                       - 180)
            if diff > 15:
                self._angle_history.clear()
                self._angle_history.append(raw_angle)
                self._last_valid_angle = raw_angle
                return raw_angle

        self._angle_history.append(raw_angle)

        if len(self._angle_history) < 2:
            self._last_valid_angle = raw_angle
            return raw_angle

        sin_sum = 0.0
        cos_sum = 0.0
        weight_sum = 0.0
        for i, a in enumerate(self._angle_history):
            w = 2.0 ** i
            sin_sum += w * math.sin(math.radians(a))
            cos_sum += w * math.cos(math.radians(a))
            weight_sum += w

        avg = math.degrees(math.atan2(sin_sum / weight_sum,
                                       cos_sum / weight_sum)) % 360
        self._last_valid_angle = avg
        return avg

    # ==================== API ====================

    def set_arrow_colors(self, color1_rgb: Tuple[int, int, int],
                         color2_rgb: Tuple[int, int, int],
                         tolerance: int = 80):
        """调整箭头颜色 (RGB 格式)"""
        self._arrow_color1 = np.array(
            [color1_rgb[2], color1_rgb[1], color1_rgb[0]], dtype=np.int16)
        self._arrow_color2 = np.array(
            [color2_rgb[2], color2_rgb[1], color2_rgb[0]], dtype=np.int16)
        self._color_tolerance = tolerance

    def reset(self):
        """Reset angle history and calibration"""
        self._angle_history.clear()
        self._last_valid_angle = None
        self._calibrated = False
        self._calib_data = []
        self._calib_crop_size = 0
