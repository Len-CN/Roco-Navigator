"""
文件操作工具

提供常用的文件和目录操作函数。
"""

import json
import os
import shutil
import sys
import logging
from typing import Any, Optional

from .app_info import APP_DATA_DIR_NAME

logger = logging.getLogger(__name__)


def get_project_root() -> str:
    """
    获取项目根目录路径
    
    Returns:
        str: 项目根目录的绝对路径
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    """判断当前是否为 PyInstaller 打包后的运行环境。"""
    return bool(getattr(sys, "frozen", False))


def get_bundled_root() -> str:
    """获取程序内置资源根目录。"""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return get_project_root()


def get_user_data_root() -> str:
    """获取用户可写数据根目录。"""
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(local_app_data, APP_DATA_DIR_NAME)
    return get_project_root()


def get_data_dir() -> str:
    """获取数据文件目录"""
    return os.path.join(get_user_data_root(), "data_files")


def get_assets_dir() -> str:
    """获取可写资源文件目录"""
    return os.path.join(get_user_data_root(), "assets")


def get_bundled_assets_dir() -> str:
    """获取随程序发布的只读资源目录。"""
    return os.path.join(get_bundled_root(), "assets")


def get_logs_dir() -> str:
    """获取日志目录"""
    return os.path.join(get_user_data_root(), "logs")


def get_packages_dir() -> str:
    """获取可选依赖安装目录。"""
    return os.path.join(get_user_data_root(), "packages")


def add_user_packages_to_path() -> str:
    """让打包版能加载用户后续安装的可选依赖。"""
    packages_dir = get_packages_dir()
    if packages_dir not in sys.path:
        sys.path.insert(0, packages_dir)

    if os.path.isdir(packages_dir):
        os.environ["PYTHONPATH"] = (
            packages_dir + os.pathsep + os.environ.get("PYTHONPATH", "")
        ).rstrip(os.pathsep)
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(packages_dir)
            except OSError:
                logger.debug("无法添加依赖 DLL 搜索目录: %s", packages_dir)

    return packages_dir


def ensure_dir(path: str) -> str:
    """
    确保目录存在，不存在则创建
    
    Args:
        path: 目录路径
        
    Returns:
        str: 目录路径
    """
    os.makedirs(path, exist_ok=True)
    return path


def load_json(filepath: str, default: Any = None) -> Any:
    """
    加载 JSON 文件
    
    Args:
        filepath: 文件路径
        default: 文件不存在或解析失败时的默认值
        
    Returns:
        解析后的数据
    """
    if not os.path.exists(filepath):
        logger.debug(f"JSON 文件不存在: {filepath}")
        return default
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {filepath}, 错误: {e}")
        return default
    except Exception as e:
        logger.error(f"读取文件失败: {filepath}, 错误: {e}")
        return default


def save_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    保存数据为 JSON 文件
    
    Args:
        filepath: 文件路径
        data: 要保存的数据
        indent: 缩进空格数
        
    Returns:
        bool: 是否成功
    """
    try:
        ensure_dir(os.path.dirname(filepath))
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"保存 JSON 失败: {filepath}, 错误: {e}")
        return False


def backup_file(filepath: str, suffix: str = ".bak") -> Optional[str]:
    """
    备份文件
    
    Args:
        filepath: 原文件路径
        suffix: 备份文件后缀
        
    Returns:
        Optional[str]: 备份文件路径，失败返回 None
    """
    if not os.path.exists(filepath):
        return None
    
    backup_path = filepath + suffix
    try:
        shutil.copy2(filepath, backup_path)
        logger.debug(f"文件已备份: {filepath} -> {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"备份文件失败: {e}")
        return None


def get_file_size(filepath: str) -> int:
    """
    获取文件大小 (字节)
    
    Args:
        filepath: 文件路径
        
    Returns:
        int: 文件大小，文件不存在返回 0
    """
    if os.path.exists(filepath):
        return os.path.getsize(filepath)
    return 0


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小
    
    Args:
        size_bytes: 字节数
        
    Returns:
        str: 格式化后的大小字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
