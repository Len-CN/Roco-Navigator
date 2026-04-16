"""
日志工具模块

提供统一的日志配置和管理。
支持文件日志和控制台日志输出。
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional


# 全局日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 文件日志格式 (更详细)
FILE_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"

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
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(base_dir, "logs")
        
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
    
    return logger
