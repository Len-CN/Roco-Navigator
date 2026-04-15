"""
侧边栏组件

提供地图控制、资源管理、导航控制等功能入口。
新拟物派设计风格。
"""

import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QScrollArea,
    QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from roco_navigator.ui.widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicSeparator, NeumorphicProgress, StatusIndicator,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_DISABLED, ACCENT, SUCCESS, WARNING, ERROR,
    apply_shadow
)

logger = logging.getLogger(__name__)


class SidebarSection(QWidget):
    """侧边栏功能区段"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(10)

        # 区段标题
        self._title = NeumorphicLabel(title.upper(), level="section")
        layout.addWidget(self._title)

        # 内容容器
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        layout.addWidget(self._content)

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)


class Sidebar(QWidget):
    """侧边栏"""

    # 信号
    calibrate_clicked = pyqtSignal()
    start_tracking_clicked = pyqtSignal()
    stop_tracking_clicked = pyqtSignal()
    plan_route_clicked = pyqtSignal()
    start_nav_clicked = pyqtSignal()
    stop_nav_clicked = pyqtSignal()
    update_points_clicked = pyqtSignal()
    update_map_clicked = pyqtSignal()
    toggle_overlay_clicked = pyqtSignal(bool)
    settings_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SECONDARY};
                border-radius: 16px;
            }}
        """)

        # 主布局使用 ScrollArea
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {BG_SECONDARY};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {TEXT_DISABLED};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 20, 16, 20)
        content_layout.setSpacing(20)

        # ---- 追踪控制 ----
        tracking_section = SidebarSection("位置追踪")

        # 追踪状态行
        status_row = QHBoxLayout()
        self._tracking_indicator = StatusIndicator()
        self._tracking_indicator.set_status("idle")
        self._tracking_status_label = NeumorphicLabel("空闲", level="body")
        status_row.addWidget(self._tracking_indicator)
        status_row.addWidget(self._tracking_status_label)
        status_row.addStretch()
        tracking_section.add_layout(status_row)

        # 校准按钮
        self._calibrate_btn = NeumorphicButton("校准小地图")
        self._calibrate_btn.clicked.connect(self.calibrate_clicked.emit)
        tracking_section.add_widget(self._calibrate_btn)

        # 开始/停止追踪
        track_row = QHBoxLayout()
        track_row.setSpacing(8)
        self._start_track_btn = NeumorphicButton("开始", primary=True)
        self._stop_track_btn = NeumorphicButton("停止")
        self._stop_track_btn.setEnabled(False)
        self._start_track_btn.clicked.connect(self._on_start_tracking)
        self._stop_track_btn.clicked.connect(self._on_stop_tracking)
        track_row.addWidget(self._start_track_btn)
        track_row.addWidget(self._stop_track_btn)
        tracking_section.add_layout(track_row)

        content_layout.addWidget(tracking_section)
        content_layout.addWidget(NeumorphicSeparator())

        # ---- 导航控制 ----
        nav_section = SidebarSection("导航")

        self._plan_btn = NeumorphicButton("规划路线")
        self._plan_btn.clicked.connect(self.plan_route_clicked.emit)
        nav_section.add_widget(self._plan_btn)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self._start_nav_btn = NeumorphicButton("开始导航", primary=True)
        self._stop_nav_btn = NeumorphicButton("停止")
        self._stop_nav_btn.setEnabled(False)
        self._start_nav_btn.clicked.connect(self._on_start_nav)
        self._stop_nav_btn.clicked.connect(self._on_stop_nav)
        nav_row.addWidget(self._start_nav_btn)
        nav_row.addWidget(self._stop_nav_btn)
        nav_section.add_layout(nav_row)

        # 导航进度
        self._nav_progress = NeumorphicProgress()
        self._nav_progress.setValue(0)
        nav_section.add_widget(self._nav_progress)

        self._nav_info_label = NeumorphicLabel("暂无活动路线", level="caption")
        nav_section.add_widget(self._nav_info_label)

        content_layout.addWidget(nav_section)
        content_layout.addWidget(NeumorphicSeparator())

        # ---- 显示控制 ----
        display_section = SidebarSection("显示")

        # 悬浮窗开关
        overlay_row = QHBoxLayout()
        overlay_label = NeumorphicLabel("悬浮窗", level="body")
        self._overlay_check = QCheckBox()
        self._overlay_check.setChecked(True)
        self._overlay_check.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 40px;
                height: 20px;
                border-radius: 10px;
                background-color: #d1d5db;
            }}
            QCheckBox::indicator:checked {{
                background-color: {ACCENT};
            }}
        """)
        self._overlay_check.stateChanged.connect(
            lambda state: self.toggle_overlay_clicked.emit(state == Qt.Checked)
        )
        overlay_row.addWidget(overlay_label)
        overlay_row.addStretch()
        overlay_row.addWidget(self._overlay_check)
        display_section.add_layout(overlay_row)

        content_layout.addWidget(display_section)
        content_layout.addWidget(NeumorphicSeparator())

        # ---- 数据管理 ----
        data_section = SidebarSection("数据")

        self._update_points_btn = NeumorphicButton("更新点位", primary=True)
        self._update_points_btn.clicked.connect(self.update_points_clicked.emit)
        data_section.add_widget(self._update_points_btn)

        self._update_map_btn = NeumorphicButton("更新地图")
        self._update_map_btn.clicked.connect(self.update_map_clicked.emit)
        data_section.add_widget(self._update_map_btn)

        self._data_info_label = NeumorphicLabel("暂无数据", level="caption")
        data_section.add_widget(self._data_info_label)

        content_layout.addWidget(data_section)
        content_layout.addWidget(NeumorphicSeparator())

        # ---- 设置 ----
        settings_section = SidebarSection("设置")

        self._settings_btn = NeumorphicButton("设置")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        settings_section.add_widget(self._settings_btn)

        content_layout.addWidget(settings_section)

        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    # ---- Public API ----
    def set_tracking_status(self, status: str, text: str):
        self._tracking_indicator.set_status(status)
        self._tracking_status_label.setText(text)

    def set_tracking_active(self, active: bool):
        self._start_track_btn.setEnabled(not active)
        self._stop_track_btn.setEnabled(active)
        if active:
            self.set_tracking_status("tracking", "追踪中...")
        else:
            self.set_tracking_status("idle", "空闲")

    def set_nav_active(self, active: bool):
        self._start_nav_btn.setEnabled(not active)
        self._stop_nav_btn.setEnabled(active)

    def set_nav_progress(self, value: int, text: str = ""):
        self._nav_progress.setValue(value)
        if text:
            self._nav_info_label.setText(text)

    def set_data_info(self, text: str):
        self._data_info_label.setText(text)

    # ---- Slots ----
    def _on_start_tracking(self):
        self.set_tracking_active(True)
        self.start_tracking_clicked.emit()

    def _on_stop_tracking(self):
        self.set_tracking_active(False)
        self.stop_tracking_clicked.emit()

    def _on_start_nav(self):
        self.set_nav_active(True)
        self.start_nav_clicked.emit()

    def _on_stop_nav(self):
        self.set_nav_active(False)
        self.stop_nav_clicked.emit()
