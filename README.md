# Roco Navigator - 洛克王国导航助手

> **AI 开发声明**：本项目在开发过程中使用了 AI 辅助编程工具（Claude Code）参与代码编写、算法优化和文档生成。所有代码均经过人工审查和测试。

---

纯视觉导航辅助工具。通过屏幕截图读取游戏小地图，利用 SIFT/LoFTR 特征匹配实时定位玩家在世界地图中的位置，支持资源点路线规划和 HUD 悬浮窗导航指引。

**仅读取屏幕像素，不注入游戏进程，不模拟键盘鼠标。**

## 功能特性

- **实时定位** - SIFT 预计算特征 + 空间索引，毫秒级匹配
- **多策略降级** - SIFT -> LoFTR (GPU) -> 颜色检测 -> 惯性预测
- **方向检测** - 小地图黄色箭头朝向识别
- **路线规划** - 支持最近邻/2-opt/K-Means 聚类/OR-Tools 求解
- **HUD 悬浮窗** - 半透明浮动小地图，方向指引，可拖拽/缩放/穿透点击
- **WIKI 集成** - 自动下载 Bilibili WIKI 大地图瓦片、资源点位坐标和图标
- **点位筛选** - 按标记类型分类显示/隐藏

## 快速开始

### 一键启动 (Windows)

双击 `start.bat`，首次运行自动完成：
1. 检测 Python 环境
2. 创建虚拟环境
3. 安装所有依赖
4. 启动程序

### 手动安装

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m roco_navigator.main
```

### 使用流程

1. **下载地图** - 侧边栏 "更新地图"，等待瓦片拼接完成
2. **更新点位** - "更新点位" 获取资源坐标和图标
3. **校准小地图** - "校准小地图"，框选游戏内小地图区域
4. **开始追踪** - 点击 "开始"，自动定位玩家位置
5. **路线规划** - 勾选目标点位，点击 "开始规划"

## 可选依赖

基础运行仅需 `requirements.txt`。以下为增强功能：

| 依赖 | 用途 | 安装命令 |
|------|------|----------|
| `torch` + `kornia` | LoFTR 深度学习匹配 (GPU加速) | `pip install torch kornia` |
| `ortools` | Google OR-Tools TSP 求解器 | `pip install ortools` |
| `opencv-contrib-python` | OpenCV CUDA 加速 | `pip install opencv-contrib-python` |

缺失时自动降级到基础算法，不影响核心功能。

## 技术架构

```
屏幕截图(mss) -> 预处理(CLAHE+圆环遮罩) -> 多策略定位 -> EMA平滑 -> 路线规划 -> HUD导航
```

**定位流水线**：SIFT 特征匹配 (Lowe's ratio test + RANSAC) 为主，LoFTR 深度学习为辅，HSV 颜色检测和惯性预测兜底。

**追踪状态机**：全局扫描 -> 精确追踪 -> 惯性导航，自适应切换。

**预计算优化**：启动时提取整张地图 SIFT 特征并建立 256px 网格空间索引，运行时仅对小地图提取特征后在网格邻域内匹配。

## 项目结构

```
roco_navigator/
  config/       配置管理
  core/         定位追踪、路线规划、导航引擎
  data/         地图管理、WIKI 数据、资源/路线
  vision/       SIFT/LoFTR 匹配、图像处理、箭头检测
  ui/           PyQt5 界面 (主窗口、地图画布、HUD、对话框)
  utils/        日志、文件工具、GPU 检测
```

## 致谢

- [Game-Map-Tracker](https://github.com/761696148/Game-Map-Tracker) - 定位算法参考，SIFT/LoFTR 混合匹配架构的灵感来源
- [Bilibili WIKI 洛克王国大地图](https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE) - 地图瓦片、资源点位坐标和图标数据来源

## 许可证

MIT License
