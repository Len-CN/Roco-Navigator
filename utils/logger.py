"""
日志工具模块

提供统一的日志配置和管理。
支持文件日志和控制台日志输出。
启动时自动清理超过 7 天的旧日志。
"""

import glob
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from .file_utils import get_logs_dir


# 全局日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 文件日志格式 (更详细)
FILE_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"

# 日志保留天数
LOG_RETENTION_DAYS = 7

# 是否已初始化
_initialized = False


def setup_logger(
    name: Optional[str] = None,
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Optional[str] = None,
) -> logging.Logger:
    """
    设置并返回一个日志记录器
    
    Args:
        name: 日志记录器名称，None 表示根记录器
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: 是否输出到文件
        log_dir: 日志文件目录
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    global _initialized
    
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if _initialized and name:
        return logger
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 控制台 handler
    if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout 
               for h in logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(console_handler)
    
    # 文件 handler
    if log_to_file:
        if log_dir is None:
            log_dir = get_logs_dir()
        
        os.makedirs(log_dir, exist_ok=True)
        
        log_filename = f"roco_navigator_{datetime.now().strftime('%Y%m%d')}.log"
        log_path = os.path.join(log_dir, log_filename)
        
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
            file_handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT, LOG_DATE_FORMAT))
            logger.addHandler(file_handler)
    
    if not name:
        _initialized = True
        # 首次初始化时清理旧日志
        if log_to_file and log_dir:
            _cleanup_old_logs(log_dir)

    return logger


def _cleanup_old_logs(log_dir: str, retention_days: int = LOG_RETENTION_DAYS):
    """
    清理超过保留天数的旧日志文件

    Args:
        log_dir: 日志目录
        retention_days: 保留天数 (默认 7 天)
    """
    cutoff = datetime.now() - timedelta(days=retention_days)
    pattern = os.path.join(log_dir, "roco_navigator_*.log")
    removed = 0

    for log_file in glob.glob(pattern):
        basename = os.path.basename(log_file)
        # 从文件名提取日期: roco_navigator_20260415.log
        try:
            date_str = basename.replace("roco_navigator_", "").replace(".log", "")
            file_date = datetime.strptime(date_str, "%Y%m%d")
            if file_date < cutoff:
                os.remove(log_file)
                removed += 1
        except (ValueError, OSError):
            continue

    if removed > 0:
        logger = logging.getLogger(__name__)
        logger.info("已清理 %d 个超过 %d 天的旧日志文件", removed, retention_days)
