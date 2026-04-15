"""
屏幕捕获模块

使用 mss 库进行高性能屏幕截图。
严格限制: 只读取屏幕像素数据，不进行任何模拟操作。
"""

import logging
import numpy as np
from typing import Optional, List, Tuple
from dataclasses import dataclass

import mss
import mss.tools

logger = logging.getLogger(__name__)


@dataclass
class MonitorInfo:
    """显示器信息"""
    id: int
    left: int
    top: int
    width: int
    height: int
    name: str = ""


class ScreenCapture:
    """
    屏幕捕获器
    
    使用 mss 进行高性能屏幕截图。
    
    合规声明:
    - 只读取屏幕像素数据
    - 不模拟任何键盘/鼠标操作
    - 不注入任何游戏进程
    """

    def __init__(self):
        self._sct: Optional[mss.mss] = None
        self._monitors: List[MonitorInfo] = []
        self._initialized = False
        self._initialize()

    def _initialize(self):
        """初始化屏幕捕获"""
        try:
            self._sct = mss.mss()
            self._refresh_monitors()
            self._initialized = True
            logger.info(f"Screen capture initialized, {len(self._monitors)} monitor(s) detected")
        except Exception as e:
            logger.error(f"Failed to initialize screen capture: {e}")
            self._initialized = False

    def _refresh_monitors(self):
        """刷新显示器列表"""
        self._monitors = []
        if self._sct is None:
            return

        for i, mon in enumerate(self._sct.monitors):
            if i == 0:
                continue  # index 0 is the "all monitors" virtual screen
            self._monitors.append(MonitorInfo(
                id=i,
                left=mon["left"],
                top=mon["top"],
                width=mon["width"],
                height=mon["height"],
                name=f"Monitor {i}"
            ))

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def get_monitors(self) -> List[MonitorInfo]:
        """获取所有显示器信息"""
        return self._monitors.copy()

    def get_primary_monitor(self) -> Optional[MonitorInfo]:
        """获取主显示器"""
        if self._monitors:
            return self._monitors[0]
        return None

    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[np.ndarray]:
        """
        捕获指定区域的屏幕图像
        
        Args:
            x: 左上角 X 坐标
            y: 左上角 Y 坐标
            width: 宽度
            height: 高度
            
        Returns:
            numpy.ndarray: BGR 格式的图像数据，失败返回 None
        """
        if not self._initialized or self._sct is None:
            logger.warning("Screen capture not initialized")
            return None

        try:
            region = {"left": x, "top": y, "width": width, "height": height}
            screenshot = self._sct.grab(region)

            # 转换为 numpy 数组 (BGRA -> BGR)
            img = np.array(screenshot)
            img = img[:, :, :3]  # 去掉 alpha 通道
            return img.copy()
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None

    def capture_full_screen(self, monitor_id: int = 1) -> Optional[np.ndarray]:
        """
        捕获整个屏幕
        
        Args:
            monitor_id: 显示器 ID (从 1 开始)
            
        Returns:
            numpy.ndarray: BGR 格式的图像数据
        """
        if not self._initialized or self._sct is None:
            return None

        try:
            monitor = self._sct.monitors[monitor_id]
            screenshot = self._sct.grab(monitor)
            img = np.array(screenshot)
            img = img[:, :, :3]
            return img.copy()
        except (IndexError, Exception) as e:
            logger.error(f"Full screen capture failed: {e}")
            return None

    def capture_minimap_region(self, region: dict) -> Optional[np.ndarray]:
        """
        捕获小地图区域
        
        Args:
            region: 小地图区域 {"x": int, "y": int, "width": int, "height": int}
            
        Returns:
            numpy.ndarray: BGR 格式的小地图图像
        """
        return self.capture_region(
            region.get("x", 0),
            region.get("y", 0),
            region.get("width", 200),
            region.get("height", 200)
        )

    def benchmark(self, region: dict = None, iterations: int = 100) -> dict:
        """
        性能基准测试
        
        Args:
            region: 截图区域，None 使用全屏
            iterations: 测试次数
            
        Returns:
            dict: 性能指标
        """
        import time

        if region is None:
            mon = self.get_primary_monitor()
            if mon is None:
                return {"error": "No monitor detected"}
            region = {"left": mon.left, "top": mon.top,
                      "width": mon.width, "height": mon.height}

        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            self.capture_region(region["left"], region["top"],
                                region["width"], region["height"])
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        return {
            "avg_ms": avg_time * 1000,
            "fps": 1.0 / avg_time if avg_time > 0 else 0,
            "min_ms": min(times) * 1000,
            "max_ms": max(times) * 1000,
            "iterations": iterations,
            "region_size": f"{region['width']}x{region['height']}"
        }

    def release(self):
        """释放资源"""
        if self._sct:
            self._sct.close()
            self._sct = None
            self._initialized = False
            logger.info("Screen capture released")

    def __del__(self):
        self.release()
