"""
侧边栏组件

提供地图控制、资源管理、导航控制等功能入口。
新拟物派设计风格。
"""

import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QScrollArea,
    QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from .neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicSeparator, NeumorphicProgress, NeumorphicComboBox,
    StatusIndicator,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_DISABLED, ACCENT, SUCCESS, WARNING, ERROR,
    apply_shadow
)
from ..dialogs.filter_dialog import FilterDialog

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

    start_nav_clicked = pyqtSignal()
    stop_nav_clicked = pyqtSignal()
    update_points_clicked = pyqtSignal()
    update_map_clicked = pyqtSignal()
    filter_type_changed = pyqtSignal(object)   # emits a set of selected mark_type_names
    plan_route_for_type = pyqtSignal(object)   # emits a set of selected mark_type_names
    select_region_for_route = pyqtSignal()   # request map canvas to enter selection mode
    route_selected_changed = pyqtSignal(object)
    route_draw_clicked = pyqtSignal()
    route_finish_clicked = pyqtSignal()
    route_cancel_clicked = pyqtSignal()
    route_save_clicked = pyqtSignal()
    route_load_clicked = pyqtSignal()
    route_rename_clicked = pyqtSignal()
    route_duplicate_clicked = pyqtSignal()
    route_delete_clicked = pyqtSignal()
    route_import_clicked = pyqtSignal()
    route_export_current_clicked = pyqtSignal()
    route_export_all_clicked = pyqtSignal()
    toggle_overlay_clicked = pyqtSignal(bool)
    overlay_passthrough_clicked = pyqtSignal(bool)
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

        # ---- 路线库 ----
        route_section = SidebarSection("路线库")

        self._route_combo = NeumorphicComboBox()
        self._route_combo.currentIndexChanged.connect(self._on_route_selected)
        route_section.add_widget(self._route_combo)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        self._route_draw_btn = NeumorphicButton("绘制", primary=True)
        self._route_finish_btn = NeumorphicButton("完成")
        self._route_draw_btn.clicked.connect(self.route_draw_clicked.emit)
        self._route_finish_btn.clicked.connect(self.route_finish_clicked.emit)
        edit_row.addWidget(self._route_draw_btn)
        edit_row.addWidget(self._route_finish_btn)
        route_section.add_layout(edit_row)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self._route_cancel_btn = NeumorphicButton("取消")
        self._route_save_btn = NeumorphicButton("保存", primary=True)
        self._route_cancel_btn.clicked.connect(self.route_cancel_clicked.emit)
        self._route_save_btn.clicked.connect(self.route_save_clicked.emit)
        save_row.addWidget(self._route_cancel_btn)
        save_row.addWidget(self._route_save_btn)
        route_section.add_layout(save_row)

        manage_row = QHBoxLayout()
        manage_row.setSpacing(8)
        self._route_load_btn = NeumorphicButton("加载")
        self._route_rename_btn = NeumorphicButton("重命名")
        self._route_load_btn.clicked.connect(self.route_load_clicked.emit)
        self._route_rename_btn.clicked.connect(self.route_rename_clicked.emit)
        manage_row.addWidget(self._route_load_btn)
        manage_row.addWidget(self._route_rename_btn)
        route_section.add_layout(manage_row)

        manage_row2 = QHBoxLayout()
        manage_row2.setSpacing(8)
        self._route_duplicate_btn = NeumorphicButton("复制")
        self._route_delete_btn = NeumorphicButton("删除")
        self._route_duplicate_btn.clicked.connect(self.route_duplicate_clicked.emit)
        self._route_delete_btn.clicked.connect(self.route_delete_clicked.emit)
        manage_row2.addWidget(self._route_duplicate_btn)
        manage_row2.addWidget(self._route_delete_btn)
        route_section.add_layout(manage_row2)

        io_row = QHBoxLayout()
        io_row.setSpacing(8)
        self._route_import_btn = NeumorphicButton("导入")
        self._route_export_current_btn = NeumorphicButton("导出当前")
        self._route_import_btn.clicked.connect(self.route_import_clicked.emit)
        self._route_export_current_btn.clicked.connect(self.route_export_current_clicked.emit)
        io_row.addWidget(self._route_import_btn)
        io_row.addWidget(self._route_export_current_btn)
        route_section.add_layout(io_row)

        self._route_export_all_btn = NeumorphicButton("导出全部")
        self._route_export_all_btn.clicked.connect(self.route_export_all_clicked.emit)
        route_section.add_widget(self._route_export_all_btn)

        self._route_info_label = NeumorphicLabel("暂无路线", level="caption")
        route_section.add_widget(self._route_info_label)

        content_layout.addWidget(route_section)
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

        # 悬浮窗穿透开关
        passthrough_row = QHBoxLayout()
        passthrough_label = NeumorphicLabel("悬浮窗穿透", level="body")
        self._overlay_passthrough_check = QCheckBox()
        self._overlay_passthrough_check.setChecked(False)
        self._overlay_passthrough_check.setStyleSheet(f"""
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
        self._overlay_passthrough_check.stateChanged.connect(
            lambda state: self.overlay_passthrough_clicked.emit(state == Qt.Checked)
        )
        passthrough_row.addWidget(passthrough_label)
        passthrough_row.addStretch()
        passthrough_row.addWidget(self._overlay_passthrough_check)
        display_section.add_layout(passthrough_row)

        content_layout.addWidget(display_section)
        content_layout.addWidget(NeumorphicSeparator())

        # ---- 数据 ----
        data_section = SidebarSection("数据")

        update_row = QHBoxLayout()
        update_row.setSpacing(8)
        self._update_points_btn = NeumorphicButton("更新点位", primary=True)
        self._update_points_btn.clicked.connect(self.update_points_clicked.emit)
        update_row.addWidget(self._update_points_btn)

        self._update_map_btn = NeumorphicButton("更新地图")
        self._update_map_btn.clicked.connect(self.update_map_clicked.emit)
        update_row.addWidget(self._update_map_btn)
        data_section.add_layout(update_row)

        data_section.add_widget(NeumorphicSeparator())

        # 点位筛选按钮 + 状态标签
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._filter_btn = NeumorphicButton("点位筛选")
        self._filter_btn.clicked.connect(self._open_filter_dialog)
        filter_row.addWidget(self._filter_btn)
        data_section.add_layout(filter_row)

        self._filter_status_label = NeumorphicLabel("显示全部", level="caption")
        data_section.add_widget(self._filter_status_label)

        # 内部状态: 筛选数据
        self._grouped_data = {}          # {type_name: [mark_type_name, ...]}
        self._point_counts = {}          # {mark_type_name: count}
        self._selected_mark_type_names = set()

        # 路线规划: 区域选择 + 规划按钮
        plan_row = QHBoxLayout()
        plan_row.setSpacing(8)

        self._plan_scope = NeumorphicComboBox()
        self._plan_scope.addItems(["全图", "框选区域"])
        self._plan_scope.setFixedWidth(110)
        plan_row.addWidget(self._plan_scope)

        self._plan_for_type_btn = NeumorphicButton("规划路线")
        self._plan_for_type_btn.clicked.connect(self._on_plan_for_type)
        plan_row.addWidget(self._plan_for_type_btn)
        data_section.add_layout(plan_row)

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

    def set_overlay_enabled(self, enabled: bool):
        self._overlay_check.blockSignals(True)
        self._overlay_check.setChecked(enabled)
        self._overlay_check.blockSignals(False)

    def set_routes(self, routes: list, current_id: str = ""):
        self._route_combo.blockSignals(True)
        self._route_combo.clear()
        self._route_combo.addItem("未选择路线", "")
        for route in routes:
            count = len(getattr(route, "points", []) or [])
            self._route_combo.addItem(f"{route.name} ({count}点)", route.id)
        index = self._route_combo.findData(current_id or "")
        self._route_combo.setCurrentIndex(index if index >= 0 else 0)
        self._route_combo.blockSignals(False)

    def selected_route_id(self) -> str:
        return self._route_combo.currentData() or ""

    def set_current_route_id(self, route_id: str):
        self._route_combo.blockSignals(True)
        index = self._route_combo.findData(route_id or "")
        self._route_combo.setCurrentIndex(index if index >= 0 else 0)
        self._route_combo.blockSignals(False)

    def set_route_info(self, point_count: int, distance: float = 0.0,
                       dirty: bool = False, editing: bool = False):
        if point_count <= 0:
            text = "暂无路线"
        else:
            dirty_text = "，未保存" if dirty else ""
            editing_text = "，编辑中" if editing else ""
            text = f"{point_count} 点，{distance:.0f}px{dirty_text}{editing_text}"
        self._route_info_label.setText(text)

    def set_route_editing_active(self, active: bool):
        self._route_draw_btn.setEnabled(not active)
        self._route_finish_btn.setEnabled(active)
        self._route_cancel_btn.setEnabled(active)

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

    def set_type_filter_items(self, types: list):
        """Set available resource types for filtering (backward compat).
        Converts flat list to grouped dict and calls set_type_filter_items_grouped.
        """
        grouped = {t: [] for t in types}
        self.set_type_filter_items_grouped(grouped)

    def set_type_filter_items_grouped(self, grouped: dict, point_counts: dict = None):
        """Store grouped mark_type_names data for the filter dialog.

        Args:
            grouped: {type_name: [mark_type_name_1, mark_type_name_2, ...], ...}
            point_counts: {mark_type_name: count, ...}
        """
        self._grouped_data = grouped
        if point_counts is not None:
            self._point_counts = point_counts

    def _get_selected_mark_type_names(self) -> set:
        """Collect all selected mark_type_names."""
        return set(self._selected_mark_type_names)

    def _open_filter_dialog(self):
        """Open the filter dialog."""
        dialog = FilterDialog(
            grouped_data=self._grouped_data,
            point_counts=self._point_counts,
            current_selection=self._selected_mark_type_names,
            parent=self,
        )
        dialog.filter_applied.connect(self._on_filter_applied)
        dialog.exec_()

    def _on_filter_applied(self, selected: set):
        """Handle filter dialog result."""
        self._selected_mark_type_names = set(selected)
        # Update status label
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

    def _on_route_selected(self, _index: int):
        self.route_selected_changed.emit(self.selected_route_id())
