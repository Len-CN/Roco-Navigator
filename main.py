"""
Roco Navigator - 洛克王国导航辅助工具
程序入口

核心定位: 纯视觉读取 + 纯路线指引 + 纯 UI 展示
严格禁止: 模拟键盘/鼠标、游戏进程注入、读写游戏内存、任何自动化操作
"""

import sys
import os

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from roco_navigator.utils.logger import setup_logger
from roco_navigator.utils.gpu_utils import GPUManager
from roco_navigator.config.settings import Settings


def check_environment():
    """检查运行环境"""
    import platform
    logger = setup_logger(__name__)
    
    logger.info("=" * 50)
    logger.info("Roco Navigator 启动")
    logger.info("=" * 50)
    logger.info(f"Python 版本: {platform.python_version()}")
    logger.info(f"操作系统: {platform.system()} {platform.release()}")
    
    # 检查核心依赖
    try:
        import cv2
        logger.info(f"OpenCV 版本: {cv2.__version__}")
    except ImportError:
        logger.error("OpenCV 未安装! 请运行: pip install opencv-python")
        return False
    
    try:
        import numpy as np
        logger.info(f"NumPy 版本: {np.__version__}")
    except ImportError:
        logger.error("NumPy 未安装! 请运行: pip install numpy")
        return False
    
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QT_VERSION_STR
        logger.info(f"PyQt5 版本: {QT_VERSION_STR}")
    except ImportError:
        logger.error("PyQt5 未安装! 请运行: pip install PyQt5")
        return False
    
    try:
        import mss
        logger.info("mss 屏幕捕获库: 已安装")
    except ImportError:
        logger.error("mss 未安装! 请运行: pip install mss")
        return False
    
    # GPU 检测
    gpu_manager = GPUManager()
    gpu_info = gpu_manager.get_gpu_info()
    if gpu_info["available"]:
        logger.info(f"GPU 加速: 可用 ({gpu_info['device_count']} 个 CUDA 设备)")
    else:
        logger.info("GPU 加速: 不可用 (将使用 CPU)")
    
    logger.info("环境检查通过")
    return True


def main():
    """主函数"""
    # 设置日志
    logger = setup_logger("roco_navigator")
    
    # 环境检查
    if not check_environment():
        logger.error("环境检查失败，程序退出")
        sys.exit(1)
    
    # 加载配置
    settings = Settings()
    settings.load()
    logger.info("配置加载完成")
    
    # 启动 PyQt5 应用
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    app.setApplicationName("Roco Navigator")
    app.setApplicationVersion("0.1.0")
    
    # TODO: 阶段 1 将实现主窗口
    # from roco_navigator.ui.main_window import MainWindow
    # window = MainWindow(settings)
    # window.show()
    
    logger.info("Roco Navigator 已启动 (阶段 0 - 框架初始化)")
    logger.info("主窗口将在阶段 1 中实现")
    
    # 暂时直接退出，阶段 1 将进入事件循环
    # sys.exit(app.exec_())
    logger.info("阶段 0 验证完成，程序正常退出")
    sys.exit(0)


if __name__ == "__main__":
    main()
