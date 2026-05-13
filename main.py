"""
Roco Navigator - 洛克王国导航辅助工具
程序入口

核心定位: 纯视觉读取 + 纯路线指引 + 纯 UI 展示
严格禁止: 模拟键盘/鼠标、游戏进程注入、读写游戏内存、任何自动化操作
"""

import sys
import os
import importlib

# 动态注册当前目录为包（无论目录叫什么名字）
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_name = os.path.basename(_pkg_dir)
_parent_dir = os.path.dirname(_pkg_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
if _pkg_name not in sys.modules:
    importlib.import_module(_pkg_name)
__package__ = _pkg_name

from .utils.file_utils import add_user_packages_to_path, get_bundled_root, is_frozen

add_user_packages_to_path()

# IMPORTANT: Import torch before PyQt5 to avoid DLL conflicts
# PyQt5 and PyTorch both use different versions of some DLLs (like c10.dll)
# Importing torch first ensures its DLLs are loaded correctly
try:
    import torch
    _TORCH_AVAILABLE = True
except (ImportError, OSError):
    _TORCH_AVAILABLE = False

from .utils.logger import setup_logger
from .utils.gpu_utils import GPUManager
from .utils.app_info import APP_DISPLAY_NAME, APP_VERSION
from .config.settings import Settings


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
        # 检测是否是 CUDA 版本
        if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
            logger.info("OpenCV 类型: opencv-contrib-python (CUDA 可用)")
        else:
            logger.info("OpenCV 类型: opencv-python (CPU)")
    except ImportError as e:
        # OpenCV CUDA 版本 DLL 加载失败，自动回退到 CPU 版本
        if "DLL load failed" in str(e) or "找不到指定的模块" in str(e):
            logger.warning("OpenCV CUDA 版本 DLL 加载失败，可能缺少 CUDA 运行时库")
            logger.info("正在自动切换到 CPU 版本...")
            
            # 自动安装 CPU 版本
            import subprocess
            try:
                from .utils.runtime import build_pip_command

                exe, args = build_pip_command(["uninstall", "opencv-contrib-python", "-y"])
                result = subprocess.run([exe] + args, capture_output=True, timeout=30)
                exe, args = build_pip_command(["install", "opencv-python"])
                result = subprocess.run([exe] + args, capture_output=True, timeout=120)
                if result.returncode == 0:
                    logger.info("已自动安装 CPU 版本，请重新启动程序")
                    logger.info("如需使用 CUDA 版本，请先安装 CUDA Toolkit 12.x/13.x")
                else:
                    logger.error("自动安装 CPU 版本失败，请重新运行 start.bat 自动修复")
            except Exception as install_error:
                logger.error(f"自动安装失败: {install_error}")
                logger.error("请重新运行 start.bat 自动修复")
            return False
        else:
            logger.error(
                "OpenCV 未安装! 请运行: pip install opencv-python\n"
                "  或在程序设置→依赖选项卡中安装。"
            )
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
    from PyQt5.QtWidgets import QApplication, QFileIconProvider
    from PyQt5.QtCore import QFileInfo
    from PyQt5.QtGui import QFont, QIcon
    from .ui.main_window import MainWindow

    # 中文路径下 Qt 可能找不到平台插件，手动指定插件目录
    import PyQt5
    qt_plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
    if os.path.isdir(qt_plugin_path):
        os.environ["QT_PLUGIN_PATH"] = qt_plugin_path

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    if is_frozen():
        icon = QFileIconProvider().icon(QFileInfo(sys.executable))
    else:
        icon_path = os.path.join(get_bundled_root(), "roco_navigator_icon.svg")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # 创建并显示主窗口
    window = MainWindow(settings)
    window.show()

    logger.info("Roco Navigator 主窗口已启动")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
