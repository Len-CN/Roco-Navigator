"""
GPU 检测和管理工具

负责检测 CUDA GPU 可用性，管理 GPU 加速的启用/禁用。
在 GPU 不可用时自动降级到 CPU。
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GPUManager:
    """GPU 管理器"""
    
    def __init__(self):
        self.gpu_available: bool = False
        self.cuda_enabled: bool = False
        self.device_count: int = 0
        self._device_info: Dict = {}
        
        self._check_gpu()
    
    def _check_gpu(self) -> None:
        """检测 GPU 是否可用"""
        try:
            import cv2
            self.device_count = cv2.cuda.getCudaEnabledDeviceCount()
            if self.device_count > 0:
                self.gpu_available = True
                self._gather_device_info()
                logger.info(f"检测到 {self.device_count} 个 CUDA 设备")
            else:
                logger.info("未检测到 CUDA 设备，将使用 CPU 模式")
        except AttributeError:
            logger.info("OpenCV 未包含 CUDA 模块，将使用 CPU 模式")
            self.gpu_available = False
        except Exception as e:
            logger.info(f"GPU 检测异常: {e}，将使用 CPU 模式")
            self.gpu_available = False
    
    def _gather_device_info(self) -> None:
        """收集 GPU 设备信息"""
        try:
            import cv2
            for i in range(self.device_count):
                cv2.cuda.setDevice(i)
                dev = cv2.cuda.getDevice()
                self._device_info[i] = {
                    "device_id": dev,
                    "name": f"CUDA Device {dev}"
                }
        except Exception as e:
            logger.debug(f"获取 GPU 设备信息失败: {e}")
    
    def check_gpu_available(self) -> bool:
        """
        检查 GPU 是否可用
        
        Returns:
            bool: GPU 是否可用
        """
        return self.gpu_available
    
    def get_gpu_info(self) -> Dict:
        """
        获取 GPU 信息
        
        Returns:
            Dict: GPU 信息字典
        """
        info = {
            "available": self.gpu_available,
            "device_count": self.device_count,
            "enabled": self.cuda_enabled,
            "devices": self._device_info
        }
        return info
    
    def enable_gpu(self, device_id: int = 0) -> bool:
        """
        启用 GPU 加速
        
        Args:
            device_id: CUDA 设备 ID
            
        Returns:
            bool: 是否成功启用
        """
        if not self.gpu_available:
            logger.warning("GPU 不可用，无法启用 GPU 加速")
            return False
        
        if device_id >= self.device_count:
            logger.error(f"无效的设备 ID: {device_id}，可用设备数: {self.device_count}")
            return False
        
        try:
            import cv2
            cv2.cuda.setDevice(device_id)
            self.cuda_enabled = True
            logger.info(f"已启用 GPU 加速 (设备 {device_id})")
            return True
        except Exception as e:
            logger.error(f"启用 GPU 失败: {e}")
            self.cuda_enabled = False
            return False
    
    def disable_gpu(self) -> None:
        """禁用 GPU 加速"""
        self.cuda_enabled = False
        logger.info("已禁用 GPU 加速，使用 CPU 模式")
    
    def get_cuda_device_count(self) -> int:
        """
        获取 CUDA 设备数量
        
        Returns:
            int: CUDA 设备数量
        """
        return self.device_count
    
    def set_cuda_device(self, device_id: int) -> bool:
        """
        设置当前 CUDA 设备
        
        Args:
            device_id: CUDA 设备 ID
            
        Returns:
            bool: 是否成功设置
        """
        return self.enable_gpu(device_id)
    
    def is_enabled(self) -> bool:
        """
        检查 GPU 加速是否已启用
        
        Returns:
            bool: 是否已启用
        """
        return self.cuda_enabled
    
    def __repr__(self) -> str:
        status = "已启用" if self.cuda_enabled else ("可用" if self.gpu_available else "不可用")
        return f"GPUManager(status={status}, devices={self.device_count})"


# 全局 GPU 管理器实例（懒加载）
_global_gpu_manager: Optional[GPUManager] = None


def get_gpu_manager() -> GPUManager:
    """
    获取全局 GPU 管理器实例
    
    Returns:
        GPUManager: GPU 管理器实例
    """
    global _global_gpu_manager
    if _global_gpu_manager is None:
        _global_gpu_manager = GPUManager()
    return _global_gpu_manager
