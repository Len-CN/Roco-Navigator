"""
设置对话框

新拟物派风格的设置界面。
"""

import logging
import sys
import os
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QCheckBox,
    QTabWidget, QWidget, QScrollArea, QTextEdit,
    QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal

from ...config.settings import Settings
from .frameless_dialog import FramelessRoundedDialog
from ..widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicSlider, NeumorphicSeparator, NeumorphicProgress,
    NeumorphicComboBox,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT,
    TEXT_DISABLED, SUCCESS, WARNING, ERROR, SHADOW_DARK,
    checkbox_qss, spinbox_qss, tab_qss, base_scrollbar_qss, font_qss
)

logger = logging.getLogger(__name__)


class SettingsDialog(FramelessRoundedDialog):
    """设置对话框"""

    settings_changed = pyqtSignal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(BG_PRIMARY, parent=parent)
        self._settings = settings
        self._main_window = parent  # MainWindow reference for install process
        self.setWindowTitle("设置")
        self.setFixedSize(550, 720)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: transparent;
            }}
            {tab_qss()}
            {spinbox_qss()}
            {checkbox_qss()}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        title = NeumorphicLabel("设置", level="title")
        layout.addWidget(title)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_tracking_tab(), "追踪")
        tabs.addTab(self._create_display_tab(), "显示")
        tabs.addTab(self._create_performance_tab(), "性能")
        tabs.addTab(self._create_navigation_tab(), "导航")
        tabs.addTab(self._create_dependencies_tab(), "功能")
        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = NeumorphicButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = NeumorphicButton("保存", primary=True)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)

        # Restore install state if process is running
        self._restore_install_state()

    def _create_row(self, label_text, widget):
        row = QHBoxLayout()
        label = NeumorphicLabel(label_text, level="body")
        label.setFixedWidth(160)
        row.addWidget(label)
        row.addWidget(widget)
        return row

    def _create_tracking_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # SIFT ratio
        self._sift_ratio = QDoubleSpinBox()
        self._sift_ratio.setRange(0.3, 0.95)
        self._sift_ratio.setSingleStep(0.05)
        self._sift_ratio.setValue(self._settings.get("minimap_detection.sift_ratio_threshold", 0.9))
        layout.addLayout(self._create_row("SIFT 比率阈值", self._sift_ratio))

        # Min matches
        self._min_matches = QSpinBox()
        self._min_matches.setRange(3, 50)
        self._min_matches.setValue(self._settings.get("minimap_detection.min_good_matches", 5))
        layout.addLayout(self._create_row("最小匹配点数", self._min_matches))

        # Use CLAHE
        self._use_clahe = QCheckBox("启用 CLAHE 图像增强")
        self._use_clahe.setChecked(self._settings.get("minimap_detection.use_clahe", True))
        layout.addWidget(self._use_clahe)

        # Use ring mask
        self._use_ring_mask = QCheckBox("启用圆环遮罩")
        self._use_ring_mask.setChecked(self._settings.get("minimap_detection.use_ring_mask", True))
        layout.addWidget(self._use_ring_mask)

        # Detection mode
        self._detection_mode = NeumorphicComboBox()
        self._detection_mode.addItems(["SIFT (经典)", "AI 智能定位", "混合 (推荐)"])
        self._detection_mode.setToolTip(
            "SIFT: 仅使用传统特征匹配（快速、无需额外依赖）\n"
            "AI 智能定位: 仅使用 DISK+LightGlue 深度学习匹配（更准确，需安装 AI 功能）\n"
            "混合: AI 优先，失败时降级到 SIFT（推荐）"
        )
        mode_map = {"sift": 0, "ai": 1, "hybrid": 2}
        current_mode = self._settings.get("tracking.detection_mode", "sift")
        self._detection_mode.setCurrentIndex(mode_map.get(current_mode, 0))
        layout.addLayout(self._create_row("识别模式", self._detection_mode))

        layout.addStretch()
        return w

    def _create_display_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Overlay opacity
        self._overlay_opacity = QDoubleSpinBox()
        self._overlay_opacity.setRange(0.3, 1.0)
        self._overlay_opacity.setSingleStep(0.05)
        self._overlay_opacity.setValue(self._settings.get("ui.overlay_opacity", 0.85))
        layout.addLayout(self._create_row("悬浮窗透明度", self._overlay_opacity))

        # Show route line
        self._show_route = QCheckBox("显示路线")
        self._show_route.setChecked(self._settings.get("ui.show_route_line", True))
        layout.addWidget(self._show_route)

        # Show distance
        self._show_distance = QCheckBox("显示距离")
        self._show_distance.setChecked(self._settings.get("ui.show_distance", True))
        layout.addWidget(self._show_distance)

        # Show compass
        self._show_compass = QCheckBox("显示指北针")
        self._show_compass.setChecked(self._settings.get("ui.show_compass", True))
        layout.addWidget(self._show_compass)

        layout.addStretch()
        return w

    def _create_performance_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Tracking interval (moved from tracking tab)
        self._track_interval = QSpinBox()
        self._track_interval.setRange(50, 1000)
        self._track_interval.setSuffix(" ms")
        self._track_interval.setValue(self._settings.get("tracking.update_interval", 100))
        layout.addLayout(self._create_row("更新间隔", self._track_interval))

        caption = NeumorphicLabel(
            "控制小地图追踪的采样频率。值越小越流畅但更耗 CPU。",
            level="body",
        )
        caption.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(11)}")
        layout.addWidget(caption)

        layout.addWidget(NeumorphicSeparator())

        # GPU type
        self._gpu_type = NeumorphicComboBox()
        self._gpu_type.addItems(["自动检测", "NVIDIA (CUDA)", "AMD/Intel (DirectML)", "仅 CPU"])
        self._gpu_type.setToolTip(
            "自动检测: 自动选择最佳 GPU\n"
            "NVIDIA: 使用 CUDA 加速（需 NVIDIA 显卡）\n"
            "AMD/Intel: 使用 DirectML 加速（需安装 AMD 显卡加速功能）\n"
            "仅 CPU: 不使用 GPU 加速"
        )
        gpu_map = {"auto": 0, "cuda": 1, "directml": 2, "cpu": 3}
        current_gpu = self._settings.get("performance.gpu_type", "auto")
        self._gpu_type.setCurrentIndex(gpu_map.get(current_gpu, 0))
        layout.addLayout(self._create_row("GPU 加速", self._gpu_type))

        gpu_caption = NeumorphicLabel(
            "选择 GPU 加速方式。AMD/Intel 显卡需在功能管理器中安装对应支持。",
            level="body",
        )
        gpu_caption.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(11)}")
        layout.addWidget(gpu_caption)

        layout.addWidget(NeumorphicSeparator())

        # Max route points
        self._max_route_points = QSpinBox()
        self._max_route_points.setRange(50, 2000)
        self._max_route_points.setSingleStep(50)
        self._max_route_points.setValue(self._settings.get("navigation.max_route_points", 500))
        layout.addLayout(self._create_row("最大规划点数", self._max_route_points))

        caption2 = NeumorphicLabel(
            "规划路线时最大允许的资源点数量。点位越多计算越慢。",
            level="body",
        )
        caption2.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(11)}")
        layout.addWidget(caption2)

        layout.addStretch()
        return w

    def _create_navigation_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Arrival distance
        self._arrival_dist = QSpinBox()
        self._arrival_dist.setRange(5, 100)
        self._arrival_dist.setSuffix(" px")
        self._arrival_dist.setValue(self._settings.get("navigation.arrival_distance", 20))
        layout.addLayout(self._create_row("到达判定距离", self._arrival_dist))

        # Route strategy
        self._strategy = NeumorphicComboBox()
        self._strategy.addItems(["自动", "最近邻", "OR-Tools"])
        self._strategy.setToolTip(
            "自动: 有 OR-Tools 时优先使用，否则用方向扫描算法\n"
            "最近邻: 贪心最近点 (最快，路线较差)\n"
            "OR-Tools: Google OR-Tools 最优求解 (需安装)"
        )
        strategy_reverse = {"auto": "自动", "nearest": "最近邻", "ortools": "OR-Tools"}
        current = self._settings.get("navigation.route_strategy", "nearest")
        display = strategy_reverse.get(current, "自动")
        idx = self._strategy.findText(display)
        if idx >= 0:
            self._strategy.setCurrentIndex(idx)
        layout.addLayout(self._create_row("路线策略", self._strategy))

        # Use 2-opt
        self._use_2opt = QCheckBox("启用 2-opt 路线优化")
        self._use_2opt.setChecked(self._settings.get("navigation.use_2opt", True))
        layout.addWidget(self._use_2opt)

        # Use teleport hubs
        self._use_teleport_hubs = QCheckBox("利用传送点中转 (缩短长距离)")
        self._use_teleport_hubs.setToolTip(
            "启用后将「传送点」视为可瞬移的中继节点。\n"
            "算法仅在中转更短时才使用传送点，不会强制访问。"
        )
        self._use_teleport_hubs.setChecked(
            self._settings.get("navigation.use_teleport_hubs", True))
        layout.addWidget(self._use_teleport_hubs)

        # Route endpoint
        self._route_endpoint = NeumorphicComboBox()
        self._route_endpoint.addItems(["开放路径 (停在最后一个点)", "回到起点 (环形)"])
        self._route_endpoint.setToolTip(
            "开放路径: 不回起点，停在最后一个点 (跑图采集推荐)\n"
            "回到起点: 路线最后回到起点 (经典 TSP)"
        )
        endpoint_reverse = {"open": "开放路径 (停在最后一个点)", "loop": "回到起点 (环形)"}
        ep_current = self._settings.get("navigation.route_endpoint", "open")
        ep_display = endpoint_reverse.get(ep_current, "开放路径 (停在最后一个点)")
        idx_ep = self._route_endpoint.findText(ep_display)
        if idx_ep >= 0:
            self._route_endpoint.setCurrentIndex(idx_ep)
        layout.addLayout(self._create_row("终点策略", self._route_endpoint))

        # Teleport cost
        self._teleport_cost = QSpinBox()
        self._teleport_cost.setRange(0, 500)
        self._teleport_cost.setSingleStep(10)
        self._teleport_cost.setSuffix(" px")
        self._teleport_cost.setValue(
            int(self._settings.get("navigation.teleport_cost_px", 150)))
        self._teleport_cost.setToolTip(
            "瞬移代价。设为 0 则积极使用传送点，\n"
            "增大可避免对短距离也走传送，让路线更连贯。"
        )
        layout.addLayout(self._create_row("传送代价", self._teleport_cost))

        layout.addStretch()
        return w

    # ── Dependencies tab ──────────────────────────────────────────────

    @staticmethod
    def _check_module_installed(module_name: str) -> bool:
        """Check if a Python module is installed."""
        import importlib.util
        return importlib.util.find_spec(module_name) is not None

    @staticmethod
    def _check_cuda_opencv() -> bool:
        """Check if OpenCV was built with CUDA support and a device is available."""
        try:
            import cv2
            return hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            return False

    def _create_dependencies_tab(self):
        """创建依赖选项卡（简化版）"""
        outer = QWidget()
        outer.setStyleSheet(f"background-color: {BG_SECONDARY};")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {BG_SECONDARY}; border: none; }}
            {base_scrollbar_qss(BG_SECONDARY, SHADOW_DARK, 8)}
        """)

        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(15)
        
        # ── 功能管理器卡片 ──
        dep_manager_card = NeumorphicCard()
        dep_manager_layout = QVBoxLayout(dep_manager_card)
        dep_manager_layout.setSpacing(10)

        dep_manager_title = NeumorphicLabel("功能管理器", level="subtitle")
        dep_manager_layout.addWidget(dep_manager_title)

        dep_manager_desc = QLabel(
            "安装可选功能以增强程序能力。\n"
            "支持断点续传、官方源下载，安全可靠。"
        )
        dep_manager_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(11)}")
        dep_manager_desc.setWordWrap(True)
        dep_manager_layout.addWidget(dep_manager_desc)

        dep_manager_btn = NeumorphicButton("打开功能管理器")
        dep_manager_btn.clicked.connect(self._open_dependency_manager)
        dep_manager_layout.addWidget(dep_manager_btn)
        
        layout.addWidget(dep_manager_card)
        
        # 分隔线
        layout.addWidget(NeumorphicSeparator())
        
        # ── 功能状态卡片 ──
        status_card = NeumorphicCard()
        status_layout = QVBoxLayout(status_card)
        status_layout.setSpacing(10)

        status_title = NeumorphicLabel("功能状态", level="subtitle")
        status_layout.addWidget(status_title)

        # 功能状态列表
        self._status_labels = {}

        features_to_check = [
            ("ai_matching", "AI 智能定位", ["torch", "kornia"]),
            ("advanced_routing", "高级路线规划", ["ortools"]),
            ("amd_gpu", "AMD/Intel 显卡加速", ["torch_directml"]),
        ]

        for key, display_name, modules in features_to_check:
            row = QHBoxLayout()

            name_label = QLabel(f"{display_name}:")
            name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; {font_qss(12)}")
            name_label.setMinimumWidth(140)
            row.addWidget(name_label)

            status_label = QLabel("检查中...")
            status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(12)}")
            self._status_labels[key] = (status_label, modules)
            row.addWidget(status_label)

            row.addStretch()
            status_layout.addLayout(row)

        # 刷新按钮
        refresh_btn = NeumorphicButton("刷新状态")
        refresh_btn.clicked.connect(self._refresh_dep_status)
        status_layout.addWidget(refresh_btn)
        
        layout.addWidget(status_card)
        
        # 分隔线
        layout.addWidget(NeumorphicSeparator())
        
        # ── 紧急修复卡片 ──
        repair_card = NeumorphicCard()
        repair_layout = QVBoxLayout(repair_card)
        repair_layout.setSpacing(10)
        
        repair_title = NeumorphicLabel("紧急修复", level="subtitle")
        repair_layout.addWidget(repair_title)
        
        repair_desc = QLabel(
            "如果程序无法启动或出现异常，点击下方按钮重新安装基础依赖。\n"
            "基础依赖包括：PyQt5、numpy、opencv-python、mss 等。"
        )
        repair_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(11)}")
        repair_desc.setWordWrap(True)
        repair_layout.addWidget(repair_desc)
        
        self._repair_btn = NeumorphicButton("修复基础依赖")
        self._repair_btn.clicked.connect(self._on_repair_base)
        repair_layout.addWidget(self._repair_btn)
        
        layout.addWidget(repair_card)
        
        # 说明文字
        layout.addSpacing(10)
        info_label = QLabel(
            "说明：\n"
            "• 使用功能管理器安装/卸载可选功能\n"
            "• 基础依赖（OpenCV、PyQt5 等）在启动时自动检查\n"
            "• NVIDIA 显卡用户安装 AI 智能定位后自动启用 GPU 加速\n"
            "• AMD/Intel 显卡用户需额外安装「AMD/Intel 显卡加速」"
        )
        info_label.setStyleSheet(f"color: {TEXT_SECONDARY}; {font_qss(10)}")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        scroll.setWidget(w)
        outer_layout.addWidget(scroll)
        
        # 初始刷新状态
        self._refresh_dep_status()
        
        return outer

    # ── Dependency helpers ────────────────────────────────────────────

    def _refresh_dep_status(self):
        """刷新功能状态"""
        import importlib
        importlib.invalidate_caches()

        for key, (status_label, modules) in self._status_labels.items():
            all_installed = all(
                self._check_module_installed(m) for m in modules
            )
            if all_installed:
                status_label.setText("✓ 已启用")
                status_label.setStyleSheet(f"color: {SUCCESS}; {font_qss(12)}")
            else:
                status_label.setText("○ 未安装")
                status_label.setStyleSheet(f"color: {TEXT_DISABLED}; {font_qss(12)}")

    def _on_repair_base(self):
        """修复基础依赖"""
        req_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            "requirements.txt"
        )
        if not os.path.exists(req_path):
            QMessageBox.warning(self, "错误", f"找不到 requirements.txt: {req_path}")
            return

        reply = QMessageBox.question(
            self, "确认修复",
            "确定要重新安装基础依赖吗？\n这将运行 pip install -r requirements.txt",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._repair_btn.setEnabled(False)
        self._repair_btn.setText("修复中...")

        from PyQt5.QtCore import QThread, pyqtSignal

        class _RepairThread(QThread):
            finished = pyqtSignal(bool, str)

            def __init__(self, req_path):
                super().__init__()
                self._req_path = req_path

            def run(self):
                import subprocess
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install",
                         "-r", self._req_path],
                        capture_output=True, text=True, timeout=300
                    )
                    if result.returncode == 0:
                        self.finished.emit(True, "基础依赖修复完成！")
                    else:
                        self.finished.emit(False, f"修复失败:\n{result.stderr[:300]}")
                except Exception as e:
                    self.finished.emit(False, f"修复过程出错:\n{str(e)}")

        def _on_repair_done(success, msg):
            self._repair_btn.setEnabled(True)
            self._repair_btn.setText("修复基础依赖")
            if success:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.critical(self, "失败", msg)

        self._repair_thread = _RepairThread(req_path)
        self._repair_thread.finished.connect(_on_repair_done)
        self._repair_thread.start()

    def _restore_install_state(self):
        """恢复安装状态（已迁移到依赖管理器）"""
        pass

    def _save_and_close(self):
        """Save all settings and close"""
        self._settings.set("tracking.update_interval", self._track_interval.value())
        self._settings.set("minimap_detection.sift_ratio_threshold", self._sift_ratio.value())
        self._settings.set("minimap_detection.min_good_matches", self._min_matches.value())
        self._settings.set("minimap_detection.use_clahe", self._use_clahe.isChecked())
        self._settings.set("minimap_detection.use_ring_mask", self._use_ring_mask.isChecked())
        # Detection mode: combo index -> key
        mode_keys = ["sift", "ai", "hybrid"]
        self._settings.set("tracking.detection_mode",
                           mode_keys[self._detection_mode.currentIndex()])
        self._settings.set("ui.overlay_opacity", self._overlay_opacity.value())
        self._settings.set("ui.show_route_line", self._show_route.isChecked())
        self._settings.set("ui.show_distance", self._show_distance.isChecked())
        self._settings.set("ui.show_compass", self._show_compass.isChecked())
        self._settings.set("navigation.arrival_distance", self._arrival_dist.value())
        strategy_map = {"自动": "auto", "最近邻": "nearest", "OR-Tools": "ortools"}
        strategy_text = self._strategy.currentText()
        self._settings.set("navigation.route_strategy", strategy_map.get(strategy_text, "auto"))
        self._settings.set("navigation.use_2opt", self._use_2opt.isChecked())
        self._settings.set("navigation.max_route_points", self._max_route_points.value())
        self._settings.set("navigation.use_teleport_hubs",
                           self._use_teleport_hubs.isChecked())
        endpoint_map = {"开放路径 (停在最后一个点)": "open", "回到起点 (环形)": "loop"}
        ep_text = self._route_endpoint.currentText()
        self._settings.set("navigation.route_endpoint",
                           endpoint_map.get(ep_text, "open"))
        self._settings.set("navigation.teleport_cost_px", self._teleport_cost.value())
        # GPU type
        gpu_keys = ["auto", "cuda", "directml", "cpu"]
        self._settings.set("performance.gpu_type", gpu_keys[self._gpu_type.currentIndex()])
        self._settings.save()
        logger.info("Settings saved")
        self.settings_changed.emit()
        self.accept()
    
    
    def _open_dependency_manager(self):
        """打开依赖管理器"""
        try:
            from .dependency_dialog import DependencyDialog
            
            dialog = DependencyDialog(self)
            dialog.exec_()
            
            # 刷新依赖状态
            self._refresh_dep_status()
            
        except Exception as e:
            logger.error(f"依赖管理器错误: {e}")
            QMessageBox.critical(
                self, "错误",
                f"启动依赖管理器失败: {e}\n\n"
                "请检查 utils/package_manager.py 是否存在。"
            )
