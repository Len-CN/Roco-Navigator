# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


ROOT = Path.cwd()
APP_VERSION = "3.0.0"

datas = []
assets_dir = ROOT / "assets"
if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

requirements = ROOT / "requirements.txt"
if requirements.exists():
    datas.append((str(requirements), "."))

datas += collect_data_files("PyQt5", includes=["Qt5/plugins/platforms/*"])
datas += collect_data_files("pip")
datas += collect_data_files("setuptools")

binaries = []
binaries += collect_dynamic_libs("cv2")
binaries += collect_dynamic_libs("PyQt5")

hiddenimports = []
hiddenimports += collect_submodules("pip")
hiddenimports += collect_submodules("setuptools")
hiddenimports += collect_submodules("wheel")
hiddenimports += [
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "cv2",
    "mss",
    "numpy",
    "PIL",
    "requests",
    "bs4",
    "lxml",
]

excludes = [
    "torch",
    "kornia",
    "torch_directml",
    "ortools",
    "pytest",
    "unittest",
]


a = Analysis(
    [str(ROOT / "build" / "pyinstaller_entry.py")],
    pathex=[str(ROOT.parent)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RocoNavigator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RocoNavigator",
)
