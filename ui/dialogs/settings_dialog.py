"""
设置对话框

新拟物派风格的设置界面。
"""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QTabWidget, QWidget, QScrollArea
)
from PyQt5.QtCore import Qt

from roco_navigator.config.settings import Settings
from roco_navigator.ui.widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicSlider, NeumorphicSeparator,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT
)

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("设置")
        self.setFixedSize(500, 600)
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
            QSpinBox, QDoubleSpinBox, QComboBox {{
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

        # Update interval
        self._track_interval = QSpinBox()
        self._track_interval.setRange(50, 1000)
        self._track_interval.setSuffix(" ms")
        self._track_interval.setValue(self._settings.get("tracking.update_interval", 100))
        layout.addLayout(self._create_row("更新间隔", self._track_interval))

        # SIFT ratio
        self._sift_ratio = QDoubleSpinBox()
        self._sift_ratio.setRange(0.3, 0.95)
        self._sift_ratio.setSingleStep(0.05)
        self._sift_ratio.setValue(self._settings.get("minimap_detection.sift_ratio_threshold", 0.7))
        layout.addLayout(self._create_row("SIFT 比率阈值", self._sift_ratio))

        # Min matches
        self._min_matches = QSpinBox()
        self._min_matches.setRange(3, 50)
        self._min_matches.setValue(self._settings.get("minimap_detection.min_good_matches", 10))
        layout.addLayout(self._create_row("最小匹配点数", self._min_matches))

        # Use CLAHE
        self._use_clahe = QCheckBox("启用 CLAHE 图像增强")
        self._use_clahe.setChecked(self._settings.get("minimap_detection.use_clahe", True))
        layout.addWidget(self._use_clahe)

        # Use ring mask
        self._use_ring_mask = QCheckBox("启用圆环遮罩")
        self._use_ring_mask.setChecked(self._settings.get("minimap_detection.use_ring_mask", True))
        layout.addWidget(self._use_ring_mask)

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

        # Max FPS
        self._max_fps = QSpinBox()
        self._max_fps.setRange(5, 60)
        self._max_fps.setSuffix(" FPS")
        self._max_fps.setValue(self._settings.get("performance.max_fps", 30))
        layout.addLayout(self._create_row("最大帧率", self._max_fps))

        # Use GPU
        self._use_gpu = QCheckBox("启用 GPU 加速 (需要 CUDA)")
        self._use_gpu.setChecked(self._settings.get("performance.use_gpu", False))
        layout.addWidget(self._use_gpu)

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
        self._strategy = QComboBox()
        self._strategy.addItems(["nearest", "optimal"])
        current = self._settings.get("navigation.route_strategy", "nearest")
        idx = self._strategy.findText(current)
        if idx >= 0:
            self._strategy.setCurrentIndex(idx)
        layout.addLayout(self._create_row("路线策略", self._strategy))

        # Use 2-opt
        self._use_2opt = QCheckBox("启用 2-opt 路线优化")
        self._use_2opt.setChecked(self._settings.get("navigation.use_2opt", True))
        layout.addWidget(self._use_2opt)

        layout.addStretch()
        return w

    def _save_and_close(self):
        """Save all settings and close"""
        self._settings.set("tracking.update_interval", self._track_interval.value())
        self._settings.set("minimap_detection.sift_ratio_threshold", self._sift_ratio.value())
        self._settings.set("minimap_detection.min_good_matches", self._min_matches.value())
        self._settings.set("minimap_detection.use_clahe", self._use_clahe.isChecked())
        self._settings.set("minimap_detection.use_ring_mask", self._use_ring_mask.isChecked())
        self._settings.set("ui.overlay_opacity", self._overlay_opacity.value())
        self._settings.set("ui.show_route_line", self._show_route.isChecked())
        self._settings.set("ui.show_distance", self._show_distance.isChecked())
        self._settings.set("ui.show_compass", self._show_compass.isChecked())
        self._settings.set("performance.max_fps", self._max_fps.value())
        self._settings.set("performance.use_gpu", self._use_gpu.isChecked())
        self._settings.set("navigation.arrival_distance", self._arrival_dist.value())
        self._settings.set("navigation.route_strategy", self._strategy.currentText())
        self._settings.set("navigation.use_2opt", self._use_2opt.isChecked())
        self._settings.save()
        logger.info("Settings saved")
        self.accept()
