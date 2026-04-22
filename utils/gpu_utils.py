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
        self.gpu_type: str = "none"  # "cuda", "directml", "none"
        self._device_info: Dict = {}

        self._check_gpu()
    
    def _check_gpu(self) -> None:
        """检测 GPU 是否可用"""
        # Method 1: OpenCV CUDA
        try:
            import cv2
            count = cv2.cuda.getCudaEnabledDeviceCount()
            if count > 0:
                self.gpu_available = True
                self.device_count = count
                self.gpu_type = "cuda"
                self._gather_device_info()
                logger.info("CUDA available via OpenCV: %d device(s)", count)
                return
        except (AttributeError, Exception):
            pass

        # Method 2: PyTorch CUDA
        try:
            import torch
            if torch.cuda.is_available():
                self.gpu_available = True
                self.device_count = torch.cuda.device_count()
                self.gpu_type = "cuda"
                for i in range(self.device_count):
                    self._device_info[i] = {
                        "device_id": i,
                        "name": torch.cuda.get_device_name(i),
                        "type": "cuda",
                    }
                logger.info("CUDA available via PyTorch: %d device(s)", self.device_count)
                return
        except Exception:
            pass

        # Method 3: DirectML (AMD/Intel GPU on Windows)
        try:
            import torch_directml
            dml_count = torch_directml.device_count()
            if dml_count > 0:
                self.gpu_available = True
                self.device_count = dml_count
                self.gpu_type = "directml"
                for i in range(dml_count):
                    self._device_info[i] = {
                        "device_id": i,
                        "name": f"DirectML Device {i}",
                        "type": "directml",
                    }
                logger.info("GPU available via DirectML: %d device(s)", dml_count)
                return
        except (ImportError, Exception):
            pass

        # Method 4: Check nvidia-smi
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                gpus = result.stdout.strip().split('\n')
                self.gpu_available = True
                self.device_count = len(gpus)
                self.gpu_type = "cuda"
                for i, name in enumerate(gpus):
                    self._device_info[i] = {
                        "device_id": i, "name": name.strip(), "type": "cuda",
                    }
                logger.info("GPU detected via nvidia-smi: %s", gpus)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        logger.info("No GPU detected, using CPU mode")
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
    
    def get_torch_device(self):
        """
        返回最佳 torch device，供 LightGlue/LoFTR 等深度学习模块使用。

        优先级: CUDA > DirectML > CPU
        """
        try:
            import torch
        except ImportError:
            return None

        if torch.cuda.is_available():
            return torch.device("cuda")

        try:
            import torch_directml
            if torch_directml.device_count() > 0:
                return torch_directml.device(0)
        except ImportError:
            pass

        return torch.device("cpu")

    def __repr__(self) -> str:
        status = "已启用" if self.cuda_enabled else ("可用" if self.gpu_available else "不可用")
        return f"GPUManager(status={status}, type={self.gpu_type}, devices={self.device_count})"


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
