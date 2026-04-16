# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

洛克王国（网页游戏）纯视觉导航辅助工具。通过屏幕截图读取小地图，SIFT/LoFTR 特征匹配定位玩家在世界地图中的位置，提供路线规划和 HUD 悬浮窗导航。

**合规底线**：仅读取屏幕像素，绝对不能添加模拟键盘/鼠标、注入游戏进程、读写游戏内存的代码。

## 运行命令

```bash
# 首次运行（Windows，自动创建 venv + 安装依赖 + 启动）
start.bat

# 手动运行
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m roco_navigator.main

# 语法检查（Windows 默认 GBK，必须指定 UTF-8）
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['file.py']]"
```

无自动化测试、无 CI/CD、无 linter 配置。`tests/` 目录存在但为空。

## 架构

Python 3.10+ / PyQt5 桌面应用，Windows 专用（mss 截屏）。

### 核心流程

```
屏幕截图(mss) -> 小地图预处理(CLAHE+圆环遮罩) -> 多策略定位 -> EMA平滑 -> 路线规划(TSP) -> HUD导航
```

### 定位流水线 (core/minimap_detector.py)

四级降级策略：**SIFT 匹配** -> LoFTR 深度学习匹配 -> HSV 颜色检测 -> 惯性预测

SIFT 匹配链路：特征提取 -> FLANN kNN -> Lowe's ratio test (阈值 0.9) -> RANSAC 单应性 (reproj_threshold=8.0) -> 透视变换得世界坐标

预计算模式：启动时对整张地图提取 SIFT 特征 + 256px 网格空间索引，运行时网格筛选近邻 + BFMatcher（局部搜索比临时建 FLANN 快）

### 追踪状态机 (core/position_tracker.py)

```
GLOBAL_SCAN --找到位置--> PRECISE_TRACK --丢失过多帧--> INERTIA_NAV --恢复/超时--> 回到前两个状态
```

- EMA 自适应平滑（alpha=0.15 慢 / 0.45 快），传送检测（200px 阈值）
- 箭头方向检测每 3 帧一次，位移方向补充计算

### 双地图架构 (data/map_manager.py)

- `logic_map`：灰度图，用于 SIFT 匹配
- `display_map`：彩色图，用于 UI 显示

### 路线规划 (core/pathfinding.py)

- 小规模 (<=20)：最近邻 + 2-opt
- 中规模：K-Means 聚类 -> 簇排序 -> 簇内 TSP
- 大规模 + OR-Tools：Guided Local Search

### WIKI 坐标系 (data/wiki_updater.py)

Bilibili WIKI 使用 Leaflet CRS.Simple，L.Transformation(1/128, 0, 1/128, 0)，缩放级别 7 时：
- `pixel_x = lng / 1 - TILE_X_MIN * 256`（TILE_X_MIN = -12，即 pixel_x = lng + 3072）
- `pixel_y = lat / 1 - TILE_Y_MIN * 256`（TILE_Y_MIN = -10，即 pixel_y = lat + 2560）
- lat 向下增大，不取反；地图尺寸 6144x5120

## 关键约束

- `torch` / `kornia`（LoFTR）和 `ortools`（TSP）是可选依赖，所有相关代码必须 try/except 包裹，缺失时降级
- SIFT 参数（ratio threshold、min matches 等）在 `data_files/config.json` 中可配置，修改时注意同步
- 配置使用点号路径访问：`settings.get("ui.overlay_enabled")`
- UI 使用新拟物派 (Neumorphism) 风格，色彩常量和组件在 `ui/widgets/neumorphic.py`
- 模块导入使用包名全路径：`from roco_navigator.xxx import ...`
- 后台任务使用 `QThread`（WIKI 更新、路线规划）
- `start.bat` 使用 `chcp 65001` + UTF-8 BOM，修改时需保持编码

## 外部数据源

- WIKI 大地图：`https://wiki.biligame.com/rocom/大地图`
- 瓦片 CDN：`https://wiki-dev-patch-oss.oss-cn-hangzhou.aliyuncs.com/res/lkwg/map-3.0/{z}/tile-{x}_{y}.png`
- 点位数据：`https://wiki.biligame.com/rocom/Data:Mapnew/point.json`
