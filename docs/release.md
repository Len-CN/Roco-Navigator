# 发布检查清单

当前安装版版本号：`3.0.0`

## 构建环境

- Windows 10/11 x64
- Python 3.10 或 3.11
- Inno Setup 6

## 构建命令

```powershell
.\scripts\build_release.ps1
```

仅构建发布产物、跳过测试：

```powershell
.\scripts\build_release.ps1 -SkipTests
```

## 发布前检查

```bat
python -m compileall main.py config core data ui utils vision tests
python -m unittest discover -s tests -v
```

## 干净机器验证

- 无 Python 环境也能启动 `RocoNavigator.exe`。
- `installer/output/RocoNavigator-3.0.0-Setup.exe` 已生成。
- `release/RocoNavigator-3.0.0-Portable.zip` 已生成，且包含 `RocoNavigator.exe`。
- 程序版本显示为 `3.0.0`。
- 用户配置、路线、日志、缓存写入 `%LOCALAPPDATA%\RocoNavigator\`。
- WIKI 地图和点位更新正常。
- 功能管理中可手动安装 `ortools`、`torch` + `kornia`、`torch-directml`。
- 卸载程序只删除安装目录，不删除 `%LOCALAPPDATA%\RocoNavigator\` 用户数据。
