# AGENTS.md

本文件记录当前仓库的项目知识，供后续 AI agent 或开发者快速接手。内容基于当前文件夹源码通读整理。

## 项目概览

`roco_navigator` 是一个 Windows 桌面端的洛克王国纯视觉导航辅助工具。它通过 `mss` 截取游戏小地图区域，用 OpenCV/SIFT、可选 LightGlue/LoFTR 等视觉匹配方法，把玩家小地图位置映射到完整世界地图上，并在 PyQt5 UI 与 HUD 悬浮窗中展示路线、目标点和导航方向。

核心边界非常重要：

- 只读取屏幕像素。
- 不模拟键盘或鼠标。
- 不注入游戏进程。
- 不读写游戏内存。
- 不添加任何自动化操作游戏的代码。

## 技术栈

- Python 3.10+
- PyQt5：桌面 UI、无边框主窗口、HUD 悬浮窗、后台 `QThread`
- OpenCV / NumPy / Pillow：图像读取、预处理、特征匹配、绘制辅助
- mss：高性能屏幕截图
- requests / BeautifulSoup / lxml：从 Bilibili WIKI 获取地图、点位和图标
- 可选依赖：
  - `torch` + `kornia`：LightGlue/LoFTR 深度学习匹配
  - `ortools`：大量点位路线规划的 TSP 求解

## 运行方式

推荐方式：

```bat
start.bat
```

手动方式：

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

也可以从父目录用包方式运行：

```bat
python -m roco_navigator.main
```

Windows 终端读取中文文件时建议显式使用 UTF-8。例如语法检查：

```bat
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read())"
```

## 当前测试情况

- `tests/test_route_manager.py` 覆盖路线保存、旧格式加载、导入冲突和导出再导入。
- 当前没有 CI/CD 或 linter 配置。
- 修改后至少应运行现有单测和 Python 语法检查；涉及 UI/视觉功能时需要人工启动程序验证。

## 目录结构

```text
roco_navigator/
├── main.py                 # 程序入口，环境检查，启动 PyQt5 主窗口
├── start.bat               # Windows 一键启动脚本，创建 venv 并安装依赖
├── requirements.txt        # 基础依赖
├── config/
│   └── settings.py         # JSON 配置管理，支持点号路径 get/set
├── core/
│   ├── screen_capture.py   # mss 截屏，仅读取屏幕像素
│   ├── minimap_detector.py # 小地图定位，多策略降级
│   ├── position_tracker.py # 三阶段追踪状态机
│   ├── pathfinding.py      # 路线规划、传送点代价、OR-Tools 降级
│   └── navigation.py       # 导航状态、目标切换、方向与 ETA
├── vision/
│   ├── image_processor.py  # CLAHE、圆环遮罩等预处理
│   ├── sift_matcher.py     # SIFT 特征匹配与预计算网格索引
│   ├── lightglue_matcher.py# 可选 DISK + LightGlue 匹配
│   ├── loftr_matcher.py    # 可选 LoFTR 匹配
│   ├── color_detector.py   # HSV 颜色检测降级
│   ├── template_matcher.py # 模板匹配
│   └── arrow_detector.py   # 玩家箭头方向检测
├── data/
│   ├── map_manager.py      # 地图加载、逻辑图/显示图、坐标转换
│   ├── resource_manager.py # 资源点加载、筛选、保存
│   ├── route_manager.py    # 路线保存与加载
│   └── wiki_updater.py     # WIKI 地图瓦片、点位、图标更新
├── ui/
│   ├── main_window.py      # 主窗口，组装所有核心模块
│   ├── map_canvas.py       # 地图画布、缩放平移、路线和点位绘制
│   ├── overlay_hud.py      # 置顶 HUD 悬浮窗
│   ├── dialogs/            # 设置、筛选、依赖安装对话框
│   └── widgets/            # 标题栏、侧边栏、新拟物控件、小地图选择器
├── utils/
│   ├── file_utils.py       # 路径、JSON、备份、文件大小工具
│   ├── logger.py           # 日志初始化和旧日志清理
│   ├── gpu_utils.py        # CUDA / DirectML / torch 设备检测
│   └── package_manager.py  # 依赖包管理辅助
├── assets/
│   ├── maps/               # WIKI 下载拼接后的地图图片
│   └── icons/wiki/         # WIKI 点位图标缓存
├── data_files/
│   ├── config.json         # 用户配置，本地生成，不追踪
│   ├── resources.json      # 本地资源点数据，不追踪
│   ├── routes.json         # 本地路线数据，不追踪
│   ├── wiki_cache.json     # WIKI 点位与标记类型缓存，不追踪
│   ├── arrow_template.npz  # 箭头检测模板，不追踪
│   └── cache/              # LightGlue/DISK 等特征缓存，不追踪
└── logs/                   # 运行日志
```

## 核心流程

整体链路：

```text
屏幕截图(mss)
  -> 小地图预处理(CLAHE + 圆环遮罩)
  -> 多策略定位(SIFT / LightGlue / LoFTR / 颜色 / 预测)
  -> PositionTracker 平滑与状态切换
  -> PathPlanner 规划路线
  -> Navigator 切换目标并计算方向
  -> MapCanvas 与 OverlayHUD 展示
```

### 启动流程

`main.py` 会：

1. 动态把当前目录注册为包，保证既能 `python main.py`，也能包方式导入。
2. 尝试先导入 `torch`，避免 PyQt5 与 PyTorch DLL 加载冲突。
3. 检查 OpenCV、NumPy、PyQt5、mss 和 GPU 状态。
4. 加载 `Settings`。
5. 创建 `QApplication` 和 `MainWindow`。

`start.bat` 会：

- 检查 Python。
- 创建 `venv`。
- 安装 `requirements.txt`。
- 失败时尝试补装依赖。
- 设置 `PYTHONPATH=%~dp0..` 后运行 `venv\Scripts\python.exe main.py`。

## 定位与追踪

主要文件：

- `core/minimap_detector.py`
- `core/position_tracker.py`
- `vision/sift_matcher.py`
- `vision/lightglue_matcher.py`
- `vision/loftr_matcher.py`
- `vision/image_processor.py`
- `vision/arrow_detector.py`

### MinimapDetector

`MinimapDetector.detect()` 的检测顺序大致为：

1. 小地图可见性检测。
2. 小地图预处理：CLAHE 增强、圆环遮罩。
3. LightGlue 预计算匹配，可选。
4. SIFT 预计算或区域匹配。
5. LoFTR 密集匹配，可选。
6. HSV 颜色检测降级。
7. 运动预测降级。

位置结果由 `DetectionResult` 表示，包括：

- `success`
- `position`
- `strategy`
- `confidence`
- `minimap_visible`
- `direction`
- `arrow_patch`

注意：

- AI 匹配依赖 `torch` / `kornia`，必须保持 try/except 降级。
- SIFT 是基础保底方案。
- `_validate_position()` 会拒绝极端跳变和明显偏离运动趋势的位置。
- 箭头方向由 `ArrowDetector` 尝试从小地图中心检测。

### PositionTracker

追踪状态机：

```text
IDLE
  -> GLOBAL_SCAN
  -> PRECISE_TRACK
  -> INERTIA_NAV
  -> GLOBAL_SCAN 或 PRECISE_TRACK
```

关键行为：

- `GLOBAL_SCAN`：全局扫描，优先使用预计算特征。
- `PRECISE_TRACK`：在上次位置附近局部搜索。
- `INERTIA_NAV`：连续丢失后尝试用更大半径恢复，否则超时回全局扫描。
- EMA 平滑用于降低位置抖动。
- 超过传送阈值时会重新全局扫描。

默认配置来自 `TrackingConfig` 与 `Settings.DEFAULTS`，例如更新间隔、传送阈值、追踪半径等。

## 地图与 WIKI 数据

主要文件：

- `data/wiki_updater.py`
- `data/map_manager.py`
- `data/resource_manager.py`
- `data/route_manager.py`

### WIKI 更新

`WikiUpdater` 从 Bilibili WIKI 获取：

- 大地图瓦片，并拼接保存为 `assets/maps/world_map_z{zoom}.png`
- 标记类型 `mark_types`
- 点位坐标 `points`
- 点位图标，保存到 `assets/icons/wiki/`

外部地址：

- WIKI 大地图：`https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE`
- 瓦片 CDN：`https://wiki-dev-patch-oss.oss-cn-hangzhou.aliyuncs.com/res/lkwg/map-3.0/{z}/tile-{x}_{y}.png`
- 点位数据：`https://wiki.biligame.com/rocom/Data:Mapnew/point.json`

### 坐标系

Bilibili WIKI 使用 Leaflet CRS.Simple。当前代码按 zoom 7 处理：

- 瓦片范围：`x = -12..11`，`y = -10..9`
- 地图尺寸：`6144 x 5120`
- `pixel_x = lng - TILE_X_MIN * 256 = lng + 3072`
- `pixel_y = lat - TILE_Y_MIN * 256 = lat + 2560`
- `lat` 向下增大，不取反。

### MapManager

维护双地图：

- `logic_map`：用于 SIFT/AI 匹配的底图。
- `display_map`：用于 UI 和 HUD 显示的地图。

目前加载时两者都来自同一张地图图片，但代码结构允许后续区分逻辑图和显示图。

## 路线规划与导航

主要文件：

- `core/pathfinding.py`
- `core/navigation.py`
- `ui/main_window.py`
- `ui/map_canvas.py`
- `ui/overlay_hud.py`

### PathPlanner

`PathPlanner.plan_route()` 返回 `RoutePlan`，包含：

- `points`
- `teleport_segments`
- `total_cost`
- `used_strategy`

路线算法：

- 小规模或 `nearest`：最近邻。
- 默认非 OR-Tools 情况：方向扫描算法。
- 可用且策略为 `auto` / `ortools`：优先 OR-Tools。
- 后处理可插入传送点 hub，降低长距离段代价。

当前只有 `mark_type_name == "传送点"` 被视为传送中继点。注释里明确庇护所不是瞬移功能。

### Navigator

`Navigator` 管理导航状态：

- `IDLE`
- `NAVIGATING`
- `ARRIVED`
- `PAUSED`

它根据玩家位置计算：

- 当前目标
- 到目标距离
- 指向目标的角度
- 八方向中文文字
- 总进度
- ETA

## UI 结构

整体由 `ui/main_window.py` 组装。

### MainWindow

职责：

- 初始化核心模块：截屏、地图、资源、路线、WIKI、检测器、追踪器、路径规划器、导航器。
- 创建无边框 PyQt5 主窗口。
- 连接侧边栏信号。
- 启动/停止追踪定时器。
- 启动 WIKI 更新和路线规划后台线程。
- 加载地图、资源点与图标。
- 把追踪和导航结果同步到地图画布与 HUD。

后台任务：

- `WikiUpdateWorker(QThread)`：下载地图或点位。
- `RouteWorker(QThread)`：规划路线，避免阻塞 UI。

### MapCanvas

功能：

- 加载和显示世界地图。
- 鼠标滚轮缩放、拖拽平移。
- 绘制资源点图标。
- 绘制玩家位置和朝向。
- 绘制路线、已访问段、传送虚线段、起点/终点。
- 支持框选区域后按当前筛选点位规划路线。
- 双击路线点可请求跳转当前目标。

### OverlayHUD

独立置顶工具窗，功能：

- 显示以玩家为中心的地图裁剪。
- 绘制玩家箭头、当前路线、目标、资源点、目标方向指示。
- 显示目标名称、距离、ETA、进度。
- 支持拖拽、边缘缩放、右键菜单、圆角矩形/圆形模式、穿透锁定。

### 视觉风格

项目 UI 使用新拟物派风格，主要色彩和基础控件在 `ui/widgets/neumorphic.py`：

- `BG_PRIMARY = "#e0e5ec"`
- `BG_SECONDARY = "#f0f0f3"`
- `ACCENT = "#667eea"`
- `SUCCESS = "#48bb78"`
- `ERROR = "#f56565"`

新增 UI 时应尽量复用这些常量和控件。

## 配置系统

`config/settings.py` 中的 `Settings`：

- 默认路径：`data_files/config.json`
- 文件不存在时会写入默认配置。
- 支持点号路径访问：

```python
settings.get("ui.overlay_enabled")
settings.set("navigation.arrival_distance", 20)
```

常见配置段：

- `minimap`：小地图区域和校准状态
- `tracking`：更新间隔、传送阈值、检测模式
- `ui`：HUD 开关、透明度、尺寸、主题
- `performance`：GPU 类型偏好
- `data_update`：WIKI 更新配置
- `minimap_detection`：SIFT、CLAHE、圆环遮罩等参数
- `ai_matching`：AI 匹配阈值和缓存
- `navigation`：到达距离、路线策略、传送点、终点策略
- `logging`：日志配置

## 依赖与降级原则

必须保持可选依赖的柔性降级：

- 没有 `torch` / `kornia` 时，AI 匹配不可用，但 SIFT 仍应工作。
- 没有 `ortools` 时，路线规划应回退到最近邻或方向扫描。
- GPU 不可用时，OpenCV/PyTorch 相关逻辑应回到 CPU。
- OpenCV CUDA DLL 加载失败时，入口代码会尝试切换到 CPU 版 OpenCV。

新增功能不要让可选依赖变成硬依赖，除非同时更新安装和降级逻辑。

## 数据文件和缓存

仓库只追踪代码、文档、启动脚本和测试。以下内容属于本机运行数据、用户数据、下载资源或缓存，默认不纳入 Git：

- `assets/maps/world_map_z6.png`
- `assets/maps/world_map_z7.png`
- `assets/icons/wiki/*.png`
- `data_files/resources.json`
- `data_files/routes.json`
- `data_files/arrow_template.npz`
- `data_files/wiki_cache.json`
- `data_files/cache/disk_features_*.npz`
- `data_files/config.json`

注意：

- 这些文件缺失时，应通过程序内更新地图/点位、首次运行配置生成或正常使用流程重新生成。
- `wiki_cache.json` 可能经常随更新变化。
- `data_files/cache/` 里的特征缓存体积较大。
- 修改代码时不要无故删除用户已有地图、图标、缓存或配置。

## 日志

`utils/logger.py`：

- 日志文件保存到 `logs/roco_navigator_YYYYMMDD.log`。
- 文件日志使用 UTF-8。
- 默认清理超过 7 天的旧日志。

## 开发注意事项

- 中文文件统一按 UTF-8 读取和写入。
- 模块内部使用相对导入较多，如 `from ..core...`；入口会动态设置包名以兼容直接运行。
- UI 后台耗时任务应使用 `QThread`，不要阻塞主线程。
- 视觉匹配相关代码需要兼顾性能，优先使用预计算特征和局部搜索。
- 截屏相关逻辑必须保持只读屏幕像素，不加入任何输入模拟。
- 路线规划返回值 `RoutePlan` 兼容旧的 list 用法，修改时注意 `__iter__`、`__getitem__`、`__len__` 行为。
- `MapCanvas` 与 `OverlayHUD` 都会绘制路线和资源点，改路线数据结构时要同步两处。
- `start.bat` 是 Windows 用户主要入口，修改时保持简单、可读、兼容中文路径。

## 推荐验证清单

完成改动后，视影响范围做以下检查：

1. 基础语法检查：

   ```bat
   python -m compileall main.py config core data ui utils vision tests
   ```

2. 单元测试：

   ```bat
   python -m unittest discover -s tests -v
   ```

3. 入口导入检查：

   ```bat
   python -c "import main"
   ```

4. UI 或追踪相关改动：

   ```bat
   python main.py
   ```

5. WIKI 更新、依赖安装、地图下载等涉及网络或环境的功能，需要在真实 Windows 环境中人工验证。
