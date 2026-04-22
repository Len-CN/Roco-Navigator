"""
全局设置管理

负责加载、保存和管理用户配置。
配置文件使用 JSON 格式存储在 data_files/config.json
"""

import json
import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Settings:
    """全局设置管理器"""
    
    # 默认配置
    DEFAULTS = {
        "minimap": {
            "region": {"x": 0, "y": 0, "width": 200, "height": 200},
            "calibrated": False
        },
        "tracking": {
            "update_interval": 100,      # 毫秒
            "position_threshold": 5,      # 像素
            "teleport_threshold": 100,    # 像素
            "max_history": 10,            # 历史位置数量
            "detection_mode": "hybrid"   # "sift", "ai", "hybrid"
        },
        "ui": {
            "overlay_enabled": True,
            "overlay_opacity": 0.85,
            "overlay_position": {"x": 50, "y": 50},
            "overlay_size": {"width": 320, "height": 400},
            "show_route_line": True,
            "show_distance": True,
            "show_compass": True,
            "theme": "neumorphism"
        },
        "performance": {
            "image_scale": 1.0,
            "gpu_type": "auto"           # "auto", "cuda", "directml", "cpu"
        },
        "data_update": {
            "wiki_url": "https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE",
            "auto_update": False,
            "update_interval_days": 7,
            "last_update": None
        },
        "minimap_detection": {
            "use_sift": True,             # 使用 SIFT 特征匹配
            "use_clahe": True,            # 使用 CLAHE 增强
            "use_ring_mask": True,        # 使用圆环遮罩
            "sift_ratio_threshold": 0.9,  # SIFT 比率测试阈值
            "min_good_matches": 5,        # 最小匹配点数
            "fallback_to_color": True,    # 降级到颜色检测
            "check_minimap_visible": True # 检查小地图可见性
        },
        "ai_matching": {
            "confidence_threshold": 0.5,  # DISK+LightGlue 匹配置信度阈值
            "min_matches": 8,             # 最小匹配点数
            "ransac_threshold": 8.0,      # RANSAC 重投影阈值
            "cache_features": True        # 缓存预计算特征到磁盘
        },
        "navigation": {
            "arrival_distance": 20,       # 到达判定距离 (像素)
            "route_strategy": "nearest",  # 默认路线策略
            "use_2opt": True,             # 使用 2-opt 优化
            "show_eta": True              # 显示预计到达时间
        },
        "logging": {
            "level": "INFO",
            "log_to_file": True,
            "log_dir": "logs",
            "max_log_files": 10
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化设置管理器
        
        Args:
            config_path: 配置文件路径，默认为 data_files/config.json
        """
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "data_files", "config.json")
        
        self._config_path = config_path
        self._config = {}
        self._load_defaults()
    
    def _load_defaults(self):
        """加载默认配置"""
        import copy
        self._config = copy.deepcopy(self.DEFAULTS)
    
    def load(self) -> bool:
        """
        从文件加载配置
        
        Returns:
            bool: 加载是否成功
        """
        if not os.path.exists(self._config_path):
            logger.info(f"配置文件不存在，使用默认配置: {self._config_path}")
            self.save()  # 保存默认配置
            return True
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            
            # 合并用户配置和默认配置（用户配置优先）
            self._merge_config(self._config, user_config)
            logger.info(f"配置已加载: {self._config_path}")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            return False
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def save(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.info(f"配置已保存: {self._config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项（支持点号分隔的键路径）
        
        Args:
            key: 配置键，如 "ui.overlay_enabled" 或 "performance.use_gpu"
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项（支持点号分隔的键路径）
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split(".")
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_section(self, section: str) -> dict:
        """
        获取配置段
        
        Args:
            section: 段名称，如 "ui", "performance"
            
        Returns:
            dict: 配置段内容
        """
        return self._config.get(section, {})
    
    def _merge_config(self, base: dict, override: dict) -> None:
        """
        递归合并配置（override 覆盖 base）
        
        Args:
            base: 基础配置
            override: 覆盖配置
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def reset(self) -> None:
        """重置为默认配置"""
        self._load_defaults()
        logger.info("配置已重置为默认值")
    
    @property
    def config_path(self) -> str:
        """获取配置文件路径"""
        return self._config_path
    
    def __repr__(self) -> str:
        return f"Settings(config_path='{self._config_path}')"
