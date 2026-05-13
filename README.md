# 洛克王国导航助手

> **声明**：本项目使用 AI 辅助开发。不保证功能可用性和稳定性，使用风险自负。本工具仅供学习交流，因使用本工具导致的任何后果（包括但不限于游戏账号封禁、数据丢失等）均由使用者自行承担，开发者不承担任何责任。

洛克王国纯视觉导航工具。它通过屏幕截图读取游戏小地图，实时识别玩家在世界地图中的位置，支持资源点路线规划和 HUD 悬浮窗导航。

本工具只读取屏幕像素，不注入游戏进程，不模拟键盘鼠标，不读写游戏内存。

## 功能

- **实时定位**：基于 SIFT 特征匹配，可选 LightGlue/LoFTR 增强匹配，实时追踪玩家位置和朝向。
- **多策略降级**：SIFT、AI 匹配、颜色检测、运动预测逐级兜底，缺少可选依赖时仍能运行基础功能。
- **路线规划**：选择目标点位后自动计算路线，支持方向扫描、OR-Tools 和最近邻策略。
- **HUD 悬浮窗**：半透明浮动小地图，显示资源图标、目标方向、距离、ETA 和进度，支持拖拽、缩放和穿透点击。
- **WIKI 集成**：从 Bilibili WIKI 下载大地图瓦片、资源点位坐标和图标。
- **点位筛选与路线管理**：按标记类型显示/隐藏资源点，支持保存、导入和导出路线。

## 快速开始

当前版本：`3.0.1`

### 安装版运行

普通用户推荐下载 `RocoNavigator-3.0.1-Setup.exe` 安装包。安装后可通过开始菜单、桌面快捷方式或安装目录中的 `RocoNavigator.exe` 启动，不需要提前安装 Python。

安装版会把用户数据写入：

```text
%LOCALAPPDATA%\RocoNavigator\
```

其中包括配置、路线、日志、WIKI 下载地图、点位缓存和可选扩展依赖。卸载程序默认只删除安装目录，不删除这些用户数据。

基础安装包不内置 `torch`、`kornia`、`torch-directml` 或 `ortools`。如需 AI 智能定位、AMD/Intel 显卡加速或高级路线规划，可在软件内“功能管理”中手动安装。

### 源码运行

#### 环境要求

- Windows 10/11
- [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 Add to PATH）

#### 启动

推荐双击 `start.bat`。首次运行会自动创建虚拟环境并安装基础依赖。

手动安装：

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

也可以从父目录以包方式运行：

```bat
python -m roco_navigator.main
```

### 使用流程

1. 点击“更新地图”，下载并拼接世界地图瓦片。
2. 点击“更新点位”，获取资源坐标和图标数据。
3. 点击“校准小地图”，框选游戏窗口中的小地图区域。
4. 点击“开始”，程序实时定位并在地图上显示玩家位置。
5. 勾选目标点位后点击“开始规划”，再点击“开始导航”启用悬浮窗指引。

## 本地数据

源码运行时，以下文件由本机运行、WIKI 更新或用户操作生成，默认不纳入 Git：

- `data_files/config.json`
- `data_files/resources.json`
- `data_files/routes.json`
- `data_files/wiki_cache.json`
- `data_files/arrow_template.npz`（内置箭头方向模板，会随源码和安装包发布）
- `data_files/cache/`
- `assets/maps/`
- `assets/icons/wiki/`
- `logs/`

如果这些文件不存在，可通过程序内“更新地图”“更新点位”和正常使用流程重新生成。

安装版对应数据目录位于 `%LOCALAPPDATA%\RocoNavigator\`。

## 可选依赖

基础功能无需额外安装。以下依赖可增强特定功能：

| 依赖 | 用途 | 安装 |
| --- | --- | --- |
| `torch` + `kornia` | LightGlue/LoFTR 深度学习匹配 | `pip install torch kornia` |
| `ortools` | 大量点位路线规划求解 | `pip install ortools` |

未安装时会自动降级，不影响核心功能。

## 技术简介

```text
屏幕截图 -> 小地图预处理 -> 多策略定位 -> EMA 平滑 -> 路线规划 -> HUD 导航
```

- **定位**：对整张地图预计算特征，运行时对小地图提取特征并在候选区域匹配。
- **追踪**：全局扫描、精确追踪、惯性导航三阶段自适应切换。
- **路线**：方向扫描算法配合 2-opt 优化，有 OR-Tools 时可使用求解器。
- **坐标系**：基于 Bilibili WIKI Leaflet CRS.Simple，zoom 7 地图尺寸为 6144 x 5120。

## 源码验证

运行现有单测：

```bat
python -m unittest discover -s tests -v
```

语法检查建议避开虚拟环境和运行缓存：

```bat
python -m compileall main.py config core data ui utils vision tests
```

涉及 UI、截图、地图下载或依赖安装的改动，需要在真实 Windows 环境中人工启动验证：

```bat
python main.py
```

## 致谢

- [Game-Map-Tracker](https://github.com/761696148/Game-Map-Tracker)：定位算法参考。
- [Bilibili WIKI 洛克王国大地图](https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE)：地图瓦片和资源点数据来源。

## 许可证

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
