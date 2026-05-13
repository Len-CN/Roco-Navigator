"""运行时辅助函数。"""

import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Tuple

from .file_utils import ensure_dir, get_user_data_root, is_frozen

PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.11.9/"
    "python-3.11.9-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def build_pip_command(pip_args: List[str]) -> Tuple[str, List[str]]:
    """生成开发版和打包版都可用的 pip 命令。"""
    if is_frozen():
        return get_managed_python(prefer_windowed=True), ["-m", "pip"] + list(pip_args)
    return sys.executable, ["-m", "pip"] + list(pip_args)


def get_managed_python(prefer_windowed: bool = False) -> str:
    """获取打包版用于安装可选依赖的独立 Python。"""
    runtime_dir = Path(get_user_data_root()) / "python-runtime"
    python_dir = runtime_dir / "python-3.11.9-embed-amd64"
    python_exe = python_dir / "python.exe"
    pythonw_exe = python_dir / "pythonw.exe"
    if python_exe.exists():
        if prefer_windowed and pythonw_exe.exists():
            return str(pythonw_exe)
        return str(python_exe)

    ensure_dir(str(runtime_dir))
    zip_path = runtime_dir / "python-3.11.9-embed-amd64.zip"
    get_pip_path = runtime_dir / "get-pip.py"

    urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(python_dir)

    pth_path = python_dir / "python311._pth"
    if pth_path.exists():
        text = pth_path.read_text(encoding="utf-8")
        text = text.replace("#import site", "import site")
        pth_path.write_text(text, encoding="utf-8")

    urllib.request.urlretrieve(GET_PIP_URL, get_pip_path)
    result = subprocess.run(
        [str(python_exe), str(get_pip_path)],
        capture_output=True,
        text=True,
        timeout=300,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)

    if prefer_windowed and pythonw_exe.exists():
        return str(pythonw_exe)
    return str(python_exe)


def hidden_subprocess_kwargs() -> dict:
    """返回 Windows 下隐藏控制台窗口的 subprocess 参数。"""
    if sys.platform != "win32":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
