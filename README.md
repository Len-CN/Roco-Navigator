# Roco Navigator - 洛克王国导航助手

纯视觉导航辅助工具。通过屏幕截图读取小地图，SIFT 特征匹配定位玩家在世界地图中的位置，提供路线规划和 HUD 悬浮窗导航。

## 功能

- **实时定位** - SIFT 特征匹配 + 预计算空间索引，帧率稳定
- **多策略降级** - SIFT -> LoFTR 深度学习 -> HSV 颜色检测 -> 惯性预测
- **方向检测** - 小地图中心黄色箭头朝向识别
- **路线规划** - 最近邻 + 2-opt / K-Means 聚类 TSP / OR-Tools 求解
- **HUD 悬浮窗** - 半透明浮动小地图 + 方向指引，可拖拽/缩放/穿透点击
- **WIKI 集成** - 自动下载大地图瓦片、点位坐标、图标资源
- **点位筛选** - 按标记类型分类显示/隐藏资源点

## 快速开始

### Windows 一键启动

双击 `start.bat`，自动创建虚拟环境、安装依赖并启动程序。

### 手动安装

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m roco_navigator.main
```

### 首次使用

1. **下载地图** - 侧边栏点击"更新地图"，等待瓦片下载完成
2. **更新点位** - 点击"更新点位"获取资源坐标数据
3. **校准小地图** - 点击"校准小地图"，框选游戏窗口中的小地图区域
4. **开始追踪** - 点击"开始"，程序自动定位并在地图上显示玩家位置
5. **路线规划** - 在地图上勾选目标点位，点击"开始规划"

## 可选依赖

基础功能仅需 `requirements.txt` 中的依赖。以下为可选增强：

| 依赖 | 用途 | 安装 |
|------|------|------|
| `torch` + `kornia` | LoFTR 深度学习匹配（SIFT 失败时降级） | `pip install torch kornia` |
| `ortools` | Google OR-Tools 高级 TSP 求解 | `pip install ortools` |
| `opencv-contrib-python` | CUDA 加速（需 CUDA Toolkit） | `pip install opencv-contrib-python` |

程序会自动检测可选依赖，缺失时降级到基础算法。

## 技术架构

```
屏幕截图(mss) -> 小地图预处理(CLAHE+圆环遮罩) -> 多策略定位 -> EMA平滑 -> 路线规划(TSP) -> HUD导航
```

### 定位流水线

| 阶段 | 算法 | 说明 |
|------|------|------|
| 预处理 | CLAHE + 圆环遮罩 | 增强对比度，去除中心玩家图标和边角UI |
| 主匹配 | SIFT + FLANN/BFMatcher | Lowe's ratio test + RANSAC homography |
| AI降级 | LoFTR (kornia) | SIFT失败时的深度学习匹配 |
| 最终降级 | HSV颜色检测 / 惯性预测 | 保持基本可用性 |

### 追踪状态机

```
GLOBAL_SCAN --找到位置--> PRECISE_TRACK --丢失过多帧--> INERTIA_NAV --恢复/超时--> 回到前两个状态
```

### WIKI 坐标系

使用 Bilibili WIKI Leaflet CRS.Simple 坐标系，zoom 7 地图 (6144x5120)：
- `pixel_x = lng - TILE_X_MIN * 256`（TILE_X_MIN = -12）
- `pixel_y = lat - TILE_Y_MIN * 256`（TILE_Y_MIN = -10）

## 项目结构

```
roco_navigator/
  config/       配置管理
  core/         定位、追踪、导航、路线规划
  data/         地图管理、WIKI数据、资源/路线管理
  ui/           PyQt5 界面（主窗口、地图画布、HUD、对话框、组件）
  vision/       SIFT/LoFTR匹配、图像处理、箭头检测
  utils/        日志、文件工具、GPU检测
```

## 合规声明

本工具仅读取屏幕像素数据用于视觉定位和路线指引。

**严格禁止**：模拟键盘/鼠标操作、注入游戏进程、读写游戏内存、任何自动化操作。

## 许可证

MIT License
