"""运行时辅助函数。"""

import sys
from typing import List, Tuple

from .file_utils import is_frozen


def build_pip_command(pip_args: List[str]) -> Tuple[str, List[str]]:
    """生成开发版和打包版都可用的 pip 命令。"""
    if is_frozen():
        return sys.executable, ["--run-pip"] + list(pip_args)
    return sys.executable, ["-m", "pip"] + list(pip_args)


def run_embedded_pip(argv: List[str]) -> int:
    """在 PyInstaller 程序内执行 pip。"""
    from pip._internal.cli.main import main as pip_main

    return int(pip_main(argv))
