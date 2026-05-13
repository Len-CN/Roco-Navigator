"""
侧边栏组件

追踪、导航、路线、显示、数据和设置功能常驻显示。
"""

import logging
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from .neumorphic import (
    NeumorphicButton, NeumorphicLabel,
    NeumorphicSeparator, NeumorphicComboBox,
    NeumorphicSwitch, StatusIndicator,
    BG_SECONDARY, TEXT_DISABLED, TEXT_SECONDARY, TEXT_PRIMARY,
    font_qss, base_scrollbar_qss
)
from ..dialogs.filter_dialog import FilterDialog

logger = logging.getLogger(__name__)


class SidebarSection(QWidget):
    """侧边栏常驻分区。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarSection")
        self.setStyleSheet(f"""
            QWidget#sidebarSection {{
                background-color: transparent;
            }}
            QLabel#sectionTitle {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
                border: none;
                padding: 0;
                {font_qss(15, 700)}
            }}
            QLabel#sectionSubtitle {{
                color: {TEXT_SECONDARY};
                background-color: transparent;
                border: none;
                padding: 0 2px;
                {font_qss(12, 400)}
            }}
            QWidget#sectionContent {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title_label)

        self._content = QWidget()
        self._content.setObjectName("sectionContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 6)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content)

    def add_widget(self, widget):
        if isinstance(widget, QLabel):
            widget.setWordWrap(True)
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)


class Sidebar(QWidget):
    """侧边栏"""

    calibrate_clicked = pyqtSignal()
    start_tracking_clicked = pyqtSignal()
    stop_tracking_clicked = pyqtSignal()
    start_nav_clicked = pyqtSignal()
    stop_nav_clicked = pyqtSignal()
    update_points_clicked = pyqtSignal()
    update_map_clicked = pyqtSignal()
    filter_type_changed = pyqtSignal(object)
    plan_route_for_type = pyqtSignal(object)
    select_region_for_route = pyqtSignal()
    toggle_overlay_clicked = pyqtSignal(bool)
    overlay_passthrough_clicked = pyqtSignal(bool)
    settings_clicked = pyqtSignal()
    route_drawer_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(270)
        self.setObjectName("sidebar")
        self.setStyleSheet(f"""
            QWidget#sidebar {{
                background-color: {BG_SECONDARY};
                border-radius: 16px;
            }}
        """)

        self._grouped_data = {}
        self._point_counts = {}
        self._selected_mark_type_names = set()

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
            {base_scrollbar_qss(BG_SECONDARY, TEXT_DISABLED, 6)}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 18, 16, 18)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._build_tracking_section())
        content_layout.addWidget(NeumorphicSeparator())
        content_layout.addWidget(self._build_navigation_section())
        content_layout.addWidget(NeumorphicSeparator())
        content_layout.addWidget(self._build_display_section())
        content_layout.addWidget(NeumorphicSeparator())
        content_layout.addWidget(self._build_route_entry_section())
        content_layout.addWidget(NeumorphicSeparator())
        content_layout.addWidget(self._build_data_section())
        content_layout.addWidget(NeumorphicSeparator())
        content_layout.addWidget(self._build_settings_section())
        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _build_tracking_section(self):
        section = SidebarSection("位置追踪")

        status_row = QHBoxLayout()
        self._tracking_indicator = StatusIndicator()
        self._tracking_indicator.set_status("idle")
        self._tracking_status_label = NeumorphicLabel("空闲", level="body")
        self._tracking_status_label.setWordWrap(True)
        self._tracking_status_label.setMinimumWidth(0)
        status_row.addWidget(self._tracking_indicator)
        status_row.addWidget(self._tracking_status_label)
        status_row.addStretch()
        section.add_layout(status_row)

        self._calibrate_btn = NeumorphicButton("校准小地图")
        self._calibrate_btn.clicked.connect(self.calibrate_clicked.emit)
        section.add_widget(self._calibrate_btn)

        track_row = QHBoxLayout()
        track_row.setSpacing(8)
        self._start_track_btn = NeumorphicButton("开始", primary=True)
        self._stop_track_btn = NeumorphicButton("停止")
        self._stop_track_btn.setEnabled(False)
        self._start_track_btn.clicked.connect(self._on_start_tracking)
        self._stop_track_btn.clicked.connect(self._on_stop_tracking)
        track_row.addWidget(self._start_track_btn)
        track_row.addWidget(self._stop_track_btn)
        section.add_layout(track_row)
        return section

    def _build_navigation_section(self):
        section = SidebarSection("导航")

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self._start_nav_btn = NeumorphicButton("开始导航", primary=True)
        self._stop_nav_btn = NeumorphicButton("停止")
        self._stop_nav_btn.setEnabled(False)
        self._start_nav_btn.clicked.connect(self._on_start_nav)
        self._stop_nav_btn.clicked.connect(self._on_stop_nav)
        nav_row.addWidget(self._start_nav_btn)
        nav_row.addWidget(self._stop_nav_btn)
        section.add_layout(nav_row)

        self._nav_info_label = NeumorphicLabel("暂无活动路线", level="caption")
        section.add_widget(self._nav_info_label)
        return section

    def _build_route_entry_section(self):
        section = SidebarSection("路线库")

        plan_row = QHBoxLayout()
        plan_row.setSpacing(8)
        self._plan_scope = NeumorphicComboBox()
        self._plan_scope.addItems(["全图", "框选区域"])
        self._plan_scope.setFixedWidth(104)
        self._plan_for_type_btn = NeumorphicButton("规划路线")
        self._plan_for_type_btn.clicked.connect(self._on_plan_for_type)
        plan_row.addWidget(self._plan_scope)
        plan_row.addWidget(self._plan_for_type_btn)
        section.add_layout(plan_row)

        section.add_widget(NeumorphicSeparator())

        self._route_summary_label = NeumorphicLabel("当前画布暂无路线", level="caption")
        section.add_widget(self._route_summary_label)

        self._open_route_drawer_btn = NeumorphicButton("进入路线库", primary=True)
        self._open_route_drawer_btn.clicked.connect(self.route_drawer_clicked.emit)
        section.add_widget(self._open_route_drawer_btn)
        return section

    def _build_display_section(self):
        section = SidebarSection("显示")

        overlay_row = QHBoxLayout()
        overlay_label = NeumorphicLabel("HUD 悬浮窗", level="body")
        overlay_label.setWordWrap(True)
        overlay_label.setMinimumWidth(0)
        self._overlay_check = NeumorphicSwitch()
        self._overlay_check.setChecked(True)
        self._overlay_check.stateChanged.connect(
            lambda state: self.toggle_overlay_clicked.emit(state == Qt.Checked)
        )
        overlay_row.addWidget(overlay_label)
        overlay_row.addStretch()
        overlay_row.addWidget(self._overlay_check)
        section.add_layout(overlay_row)

        passthrough_row = QHBoxLayout()
        passthrough_label = NeumorphicLabel("悬浮窗穿透", level="body")
        passthrough_label.setWordWrap(True)
        passthrough_label.setMinimumWidth(0)
        self._overlay_passthrough_check = NeumorphicSwitch()
        self._overlay_passthrough_check.setChecked(False)
        self._overlay_passthrough_check.stateChanged.connect(
            lambda state: self.overlay_passthrough_clicked.emit(state == Qt.Checked)
        )
        passthrough_row.addWidget(passthrough_label)
        passthrough_row.addStretch()
        passthrough_row.addWidget(self._overlay_passthrough_check)
        section.add_layout(passthrough_row)
        return section

    def _build_data_section(self):
        section = SidebarSection("数据")

        update_row = QHBoxLayout()
        update_row.setSpacing(8)
        self._update_points_btn = NeumorphicButton("更新点位", primary=True)
        self._update_map_btn = NeumorphicButton("更新地图")
        self._update_points_btn.clicked.connect(self.update_points_clicked.emit)
        self._update_map_btn.clicked.connect(self.update_map_clicked.emit)
        update_row.addWidget(self._update_points_btn)
        update_row.addWidget(self._update_map_btn)
        section.add_layout(update_row)

        section.add_widget(NeumorphicSeparator())

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._filter_btn = NeumorphicButton("点位筛选")
        self._filter_btn.clicked.connect(self._open_filter_dialog)
        filter_row.addWidget(self._filter_btn)
        section.add_layout(filter_row)

        self._filter_status_label = NeumorphicLabel("显示全部", level="caption")
        section.add_widget(self._filter_status_label)

        self._data_info_label = NeumorphicLabel("暂无数据", level="caption")
        section.add_widget(self._data_info_label)
        return section

    def _build_settings_section(self):
        section = SidebarSection("设置")
        self._settings_btn = NeumorphicButton("打开设置")
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        section.add_widget(self._settings_btn)
        return section

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
        if text:
            self._nav_info_label.setText(text)

    def set_data_info(self, text: str):
        self._data_info_label.setText(text)

    def set_overlay_enabled(self, enabled: bool):
        self._overlay_check.blockSignals(True)
        self._overlay_check.setChecked(enabled)
        self._overlay_check.blockSignals(False)
        self._overlay_passthrough_check.blockSignals(True)
        if not enabled:
            self._overlay_passthrough_check.setChecked(False)
        self._overlay_passthrough_check.setEnabled(enabled)
        self._overlay_passthrough_check.blockSignals(False)

    def set_route_summary(self, point_count: int, distance: float = 0.0,
                          dirty: bool = False, editing: bool = False):
        if point_count <= 0:
            text = "当前画布暂无路线"
        else:
            dirty_text = "，未保存" if dirty else ""
            editing_text = "，编辑中" if editing else ""
            text = f"{point_count} 点，{distance:.0f}px{dirty_text}{editing_text}"
        self._route_summary_label.setText(text)

    def set_type_filter_items(self, types: list):
        grouped = {t: [] for t in types}
        self.set_type_filter_items_grouped(grouped)

    def set_type_filter_items_grouped(self, grouped: dict, point_counts: dict = None):
        self._grouped_data = grouped
        if point_counts is not None:
            self._point_counts = point_counts

    def _get_selected_mark_type_names(self) -> set:
        return set(self._selected_mark_type_names)

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

    def _open_filter_dialog(self):
        dialog = FilterDialog(
            grouped_data=self._grouped_data,
            point_counts=self._point_counts,
            current_selection=self._selected_mark_type_names,
            parent=self,
        )
        dialog.filter_applied.connect(self._on_filter_applied)
        dialog.exec_()

    def _on_filter_applied(self, selected: set):
        self._selected_mark_type_names = set(selected)
        if not selected:
            self._filter_status_label.setText("显示全部")
        else:
            self._filter_status_label.setText(f"已选 {len(selected)} 种")
        self.filter_type_changed.emit(selected)

    def _on_plan_for_type(self):
        if self._plan_scope.currentText() == "框选区域":
            self.select_region_for_route.emit()
        else:
            selected = self._get_selected_mark_type_names()
            self.plan_route_for_type.emit(selected)
