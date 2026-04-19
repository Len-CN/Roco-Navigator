"""
设置对话框

新拟物派风格的设置界面。
"""

import logging
import sys
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QCheckBox,
    QTabWidget, QWidget, QScrollArea, QTextEdit,
    QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QProcess, QTimer

from ...config.settings import Settings
from ..widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicSlider, NeumorphicSeparator, NeumorphicProgress,
    NeumorphicComboBox,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT,
    TEXT_DISABLED, SUCCESS, WARNING, ERROR, SHADOW_DARK
)

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """设置对话框"""

    settings_changed = pyqtSignal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._main_window = parent  # MainWindow reference for install process
        self.setWindowTitle("设置")
        self.setFixedSize(550, 720)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_PRIMARY};
            }}
            QTabWidget::pane {{
                background-color: {BG_SECONDARY};
                border: none;
                border-radius: 12px;
            }}
            QTabBar::tab {{
                background-color: {BG_PRIMARY};
                color: {TEXT_SECONDARY};
                padding: 10px 20px;
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 2px;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
                font-weight: 600;
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 13px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 4px;
                background-color: {BG_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = NeumorphicLabel("设置", level="title")
        layout.addWidget(title)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_tracking_tab(), "追踪")
        tabs.addTab(self._create_display_tab(), "显示")
        tabs.addTab(self._create_performance_tab(), "性能")
        tabs.addTab(self._create_navigation_tab(), "导航")
        tabs.addTab(self._create_dependencies_tab(), "依赖")
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
        self._detection_mode.addItems(["SIFT (默认)", "LoFTR AI", "混合 (SIFT+AI)"])
        self._detection_mode.setToolTip(
            "SIFT: 仅使用传统特征匹配 (快速、稳定)\n"
            "LoFTR AI: 仅使用深度学习匹配 (抗干扰强，需GPU)\n"
            "混合: SIFT 优先，失败时切换 AI (推荐有GPU时使用)"
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
        caption.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(caption)

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
        caption2.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
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
            QScrollBar:vertical {{
                background: {BG_SECONDARY}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {SHADOW_DARK}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_SECONDARY};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(15)
        
        # ── 依赖管理器卡片 ──
        dep_manager_card = NeumorphicCard()
        dep_manager_layout = QVBoxLayout(dep_manager_card)
        dep_manager_layout.setSpacing(10)
        
        dep_manager_title = NeumorphicLabel("依赖管理器", level="subtitle")
        dep_manager_layout.addWidget(dep_manager_title)
        
        dep_manager_desc = QLabel(
            "使用依赖管理器安装和管理所有可选依赖包。\n"
            "支持断点续传、官方源下载，安全可靠。"
        )
        dep_manager_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        dep_manager_desc.setWordWrap(True)
        dep_manager_layout.addWidget(dep_manager_desc)
        
        dep_manager_btn = NeumorphicButton("打开依赖管理器")
        dep_manager_btn.clicked.connect(self._open_dependency_manager)
        dep_manager_layout.addWidget(dep_manager_btn)
        
        layout.addWidget(dep_manager_card)
        
        # 分隔线
        layout.addWidget(NeumorphicSeparator())
        
        # ── 依赖状态卡片 ──
        status_card = NeumorphicCard()
        status_layout = QVBoxLayout(status_card)
        status_layout.setSpacing(10)
        
        status_title = NeumorphicLabel("依赖状态", level="subtitle")
        status_layout.addWidget(status_title)
        
        # 状态列表
        self._status_labels = {}
        
        deps_to_check = [
            ("opencv", "OpenCV", ["cv2"]),
            ("pytorch", "PyTorch", ["torch"]),
            ("kornia", "Kornia", ["kornia"]),
            ("ortools", "OR-Tools", ["ortools"])
        ]
        
        for key, display_name, modules in deps_to_check:
            row = QHBoxLayout()
            
            name_label = QLabel(f"{display_name}:")
            name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
            name_label.setMinimumWidth(100)
            row.addWidget(name_label)
            
            status_label = QLabel("检查中...")
            status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            self._status_labels[key] = status_label
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
        repair_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
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
            "• 使用依赖管理器可以安装/卸载所有可选依赖\n"
            "• 基础依赖会在程序启动时自动检查和修复\n"
            "• OpenCV CUDA 版本如果加载失败会自动切换到 CPU 版本"
        )
        info_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
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
        """刷新依赖状态"""
        import importlib
        importlib.invalidate_caches()
        
        # 检查 OpenCV
        opencv_installed = self._check_module_installed("cv2")
        if opencv_installed:
            self._status_labels["opencv"].setText("✓ 已安装")
            self._status_labels["opencv"].setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        else:
            self._status_labels["opencv"].setText("○ 未安装")
            self._status_labels["opencv"].setStyleSheet(f"color: {TEXT_DISABLED}; font-size: 12px;")
        
        # 检查 PyTorch
        pytorch_installed = self._check_module_installed("torch")
        if pytorch_installed:
            self._status_labels["pytorch"].setText("✓ 已安装")
            self._status_labels["pytorch"].setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        else:
            self._status_labels["pytorch"].setText("○ 未安装")
            self._status_labels["pytorch"].setStyleSheet(f"color: {TEXT_DISABLED}; font-size: 12px;")
        
        # 检查 Kornia
        kornia_installed = self._check_module_installed("kornia")
        if kornia_installed:
            self._status_labels["kornia"].setText("✓ 已安装")
            self._status_labels["kornia"].setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        else:
            self._status_labels["kornia"].setText("○ 未安装")
            self._status_labels["kornia"].setStyleSheet(f"color: {TEXT_DISABLED}; font-size: 12px;")
        
        # 检查 OR-Tools
        ortools_installed = self._check_module_installed("ortools")
        if ortools_installed:
            self._status_labels["ortools"].setText("✓ 已安装")
            self._status_labels["ortools"].setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        else:
            self._status_labels["ortools"].setText("○ 未安装")
            self._status_labels["ortools"].setStyleSheet(f"color: {TEXT_DISABLED}; font-size: 12px;")

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

        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                QMessageBox.information(self, "成功", "基础依赖修复完成！")
            else:
                QMessageBox.critical(self, "失败", f"修复失败:\n{result.stderr[:300]}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"修复过程出错:\n{str(e)}")
        finally:
            self._repair_btn.setEnabled(True)
            self._repair_btn.setText("修复基础依赖")

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
