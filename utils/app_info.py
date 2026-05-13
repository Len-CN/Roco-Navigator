"""应用元信息。"""

import os
import sys

APP_NAME = "Roco Navigator"
APP_DISPLAY_NAME = "洛克导航"
APP_VERSION = "3.0.0"
APP_DATA_DIR_NAME = "RocoNavigator"
APP_ICON_FILENAME = "RocoNavigator.ico"
APP_SOURCE_ICON_FILENAME = "roco_navigator_icon.svg"


def get_app_icon_path() -> str:
    """获取当前运行环境的应用图标路径。"""
    if getattr(sys, "frozen", False):
        icon_path = os.path.join(os.path.dirname(sys.executable), APP_ICON_FILENAME)
        if os.path.exists(icon_path):
            return icon_path
        return sys.executable

    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        APP_SOURCE_ICON_FILENAME,
    )
