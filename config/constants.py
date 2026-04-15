"""
常量定义

包含项目中使用的所有常量值。
"""

# ==================== 项目信息 ====================
APP_NAME = "Roco Navigator"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "洛克王国导航辅助工具"

# ==================== 合规声明 ====================
COMPLIANCE_NOTICE = """
Roco Navigator 是一个纯视觉导航辅助工具。

允许的操作:
- 截图屏幕画面
- 分析图像内容
- 显示导航信息
- 更新本地数据

严格禁止:
- 模拟键盘按键
- 模拟鼠标点击
- 游戏进程注入
- 读写游戏内存
- 任何自动化操作
"""

# ==================== UI 设计常量 (新拟物派) ====================

# 色彩系统
class Colors:
    """新拟物派色彩系统"""
    # 背景色
    BACKGROUND = "#e0e5ec"
    BACKGROUND_DARK = "#d1d5db"
    
    # 文字色
    TEXT_PRIMARY = "#4a5568"
    TEXT_SECONDARY = "#718096"
    TEXT_LIGHT = "#a0aec0"
    
    # 强调色
    ACCENT = "#667eea"
    ACCENT_LIGHT = "#7c93ed"
    ACCENT_DARK = "#5a6fd6"
    
    # 状态色
    SUCCESS = "#48bb78"
    WARNING = "#ed8936"
    ERROR = "#f56565"
    INFO = "#4299e1"
    
    # 阴影色
    SHADOW_DARK = "#b8bcc2"
    SHADOW_LIGHT = "#ffffff"
    
    # 导航相关
    PLAYER_MARKER = "#f56565"         # 玩家标记 (红色)
    ROUTE_LINE = "#667eea"            # 路线 (蓝紫色)
    TARGET_MARKER = "#48bb78"         # 目标标记 (绿色)
    COMPASS_NORTH = "#f56565"         # 指北针北方 (红色)


# 阴影系统
class Shadows:
    """新拟物派阴影系统"""
    # 凸起效果
    RAISED = "8px 8px 16px #b8bcc2, -8px -8px 16px #ffffff"
    RAISED_SMALL = "4px 4px 8px #b8bcc2, -4px -4px 8px #ffffff"
    
    # 内凹效果
    INSET = "inset 4px 4px 8px #b8bcc2, inset -4px -4px 8px #ffffff"
    INSET_DEEP = "inset 6px 6px 12px #b8bcc2, inset -6px -6px 12px #ffffff"


# 圆角
class BorderRadius:
    """圆角常量"""
    SMALL = 8
    MEDIUM = 12
    LARGE = 16
    XLARGE = 24
    ROUND = 50  # 百分比，用于圆形


# ==================== 悬浮窗 HUD 常量 ====================

class HUD:
    """悬浮窗 HUD 常量"""
    # 默认尺寸
    DEFAULT_WIDTH = 320
    DEFAULT_HEIGHT = 400
    
    # 地图区域
    MAP_SIZE = 300
    MAP_PADDING = 10
    MAP_BORDER_RADIUS = 12
    
    # 玩家标记
    PLAYER_ARROW_SIZE = 15    # 箭头大小
    PLAYER_DOT_RADIUS = 5    # 圆点半径
    
    # 指北针
    COMPASS_RADIUS = 20
    COMPASS_OFFSET = 30       # 距离右上角的偏移
    
    # 信息区域
    INFO_HEIGHT = 70
    INFO_PADDING = 10
    
    # 路线
    ROUTE_LINE_WIDTH = 3
    ROUTE_POINT_RADIUS = 6


# ==================== 小地图检测常量 ====================

class MinimapDetection:
    """小地图检测常量"""
    # SIFT 参数
    SIFT_FEATURES = 0           # 0 表示检测所有特征
    SIFT_RATIO_THRESHOLD = 0.7  # Lowe's ratio test
    MIN_GOOD_MATCHES = 10       # 最小有效匹配数
    
    # CLAHE 参数
    CLAHE_CLIP_LIMIT = 2.0
    CLAHE_TILE_SIZE = (8, 8)
    
    # 圆环遮罩参数
    RING_MASK_OUTER_RATIO = 0.95   # 外圆半径比率
    RING_MASK_INNER_RATIO = 0.0    # 内圆半径比率 (0 = 无内圆)
    
    # 可见性检测
    VISIBILITY_THRESHOLD = 0.6
    VISIBILITY_EDGE_RATIO = 0.05
    VISIBILITY_STD_THRESHOLD = 10
    
    # 隐藏计数阈值
    HIDDEN_COUNT_THRESHOLD = 5


# ==================== 位置追踪常量 ====================

class Tracking:
    """位置追踪常量"""
    # 追踪状态
    STATE_IDLE = "idle"
    STATE_GLOBAL_SCAN = "global_scan"       # 全局扫描
    STATE_PRECISE_TRACK = "precise_track"   # 精确追踪
    STATE_INERTIA_NAV = "inertia_nav"       # 惯性导航
    
    # 阈值
    DEFAULT_UPDATE_INTERVAL = 100   # 毫秒
    MAX_MOVE_SPEED = 100            # 最大移动速度 (像素/帧)
    TELEPORT_THRESHOLD = 200        # 传送检测阈值
    POSITION_HISTORY_SIZE = 10      # 位置历史记录数量


# ==================== 路径规划常量 ====================

class PathPlanning:
    """路径规划常量"""
    STRATEGY_NEAREST = "nearest"    # 最近邻
    STRATEGY_OPTIMAL = "optimal"    # 2-opt 优化
    STRATEGY_CUSTOM = "custom"      # 自定义
    
    # 2-opt 参数
    OPT2_MAX_ITERATIONS = 1000
    OPT2_IMPROVEMENT_THRESHOLD = 0.001


# ==================== 导航常量 ====================

class Navigation:
    """导航常量"""
    DEFAULT_ARRIVAL_DISTANCE = 20   # 到达判定距离 (像素)
    DEFAULT_SPEED_ESTIMATE = 5.0    # 预估移动速度 (像素/秒)


# ==================== 数据源常量 ====================

class DataSource:
    """数据源常量"""
    WIKI_BASE_URL = "https://wiki.biligame.com/rocom"
    WIKI_MAP_URL = "https://wiki.biligame.com/rocom/%E5%A4%A7%E5%9C%B0%E5%9B%BE"
    
    # 数据文件名
    CONFIG_FILE = "config.json"
    RESOURCES_FILE = "resources.json"
    ROUTES_FILE = "routes.json"
    WIKI_CACHE_FILE = "wiki_cache.json"


# ==================== 文件路径常量 ====================

class Paths:
    """路径常量"""
    ASSETS_DIR = "assets"
    MAPS_DIR = "assets/maps"
    TEMPLATES_DIR = "assets/templates"
    ICONS_DIR = "assets/icons"
    WIKI_ICONS_DIR = "assets/icons/wiki"
    STYLES_DIR = "assets/styles"
    DATA_DIR = "data_files"
    LOGS_DIR = "logs"
