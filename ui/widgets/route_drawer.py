"""路线库抽屉组件。"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

from .neumorphic import (
    NeumorphicButton, NeumorphicComboBox, NeumorphicLabel,
    NeumorphicSeparator, BG_SECONDARY, BG_CARD, TEXT_SECONDARY,
    RADIUS_LG, base_scrollbar_qss
)


class RouteDrawer(QWidget):
    """附着在主窗口右侧的路线库操作面板。"""

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
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setObjectName("routeDrawer")
        self.setStyleSheet(f"""
            QWidget#routeDrawer {{
                background-color: {BG_SECONDARY};
                border-radius: {RADIUS_LG}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = NeumorphicLabel("路线库", level="title")
        header.addWidget(title)
        header.addStretch()
        close_btn = NeumorphicButton("收起")
        close_btn.setFixedWidth(72)
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self._summary_label = NeumorphicLabel("暂无路线", level="caption")
        layout.addWidget(self._summary_label)

        layout.addWidget(NeumorphicSeparator())

        self._route_combo = NeumorphicComboBox()
        self._route_combo.currentIndexChanged.connect(self._on_route_selected)
        layout.addWidget(self._route_combo)

        self._route_info_label = NeumorphicLabel("暂无路线", level="caption")
        layout.addWidget(self._route_info_label)

        layout.addWidget(NeumorphicSeparator())

        edit_label = NeumorphicLabel("编辑", level="section")
        layout.addWidget(edit_label)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        self._route_draw_btn = NeumorphicButton("绘制 / 编辑", primary=True)
        self._route_finish_btn = NeumorphicButton("完成")
        self._route_draw_btn.clicked.connect(self.route_draw_clicked.emit)
        self._route_finish_btn.clicked.connect(self.route_finish_clicked.emit)
        edit_row.addWidget(self._route_draw_btn)
        edit_row.addWidget(self._route_finish_btn)
        layout.addLayout(edit_row)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self._route_cancel_btn = NeumorphicButton("取消")
        self._route_save_btn = NeumorphicButton("保存", primary=True)
        self._route_cancel_btn.clicked.connect(self.route_cancel_clicked.emit)
        self._route_save_btn.clicked.connect(self.route_save_clicked.emit)
        save_row.addWidget(self._route_cancel_btn)
        save_row.addWidget(self._route_save_btn)
        layout.addLayout(save_row)

        layout.addWidget(NeumorphicSeparator())

        manage_label = NeumorphicLabel("管理", level="section")
        layout.addWidget(manage_label)

        load_row = QHBoxLayout()
        load_row.setSpacing(8)
        self._route_load_btn = NeumorphicButton("加载")
        self._route_rename_btn = NeumorphicButton("重命名")
        self._route_load_btn.clicked.connect(self.route_load_clicked.emit)
        self._route_rename_btn.clicked.connect(self.route_rename_clicked.emit)
        load_row.addWidget(self._route_load_btn)
        load_row.addWidget(self._route_rename_btn)
        layout.addLayout(load_row)

        manage_row = QHBoxLayout()
        manage_row.setSpacing(8)
        self._route_duplicate_btn = NeumorphicButton("复制")
        self._route_delete_btn = NeumorphicButton("删除", danger=True)
        self._route_duplicate_btn.clicked.connect(self.route_duplicate_clicked.emit)
        self._route_delete_btn.clicked.connect(self.route_delete_clicked.emit)
        manage_row.addWidget(self._route_duplicate_btn)
        manage_row.addWidget(self._route_delete_btn)
        layout.addLayout(manage_row)

        io_row = QHBoxLayout()
        io_row.setSpacing(8)
        self._route_import_btn = NeumorphicButton("导入")
        self._route_export_current_btn = NeumorphicButton("导出当前")
        self._route_import_btn.clicked.connect(self.route_import_clicked.emit)
        self._route_export_current_btn.clicked.connect(self.route_export_current_clicked.emit)
        io_row.addWidget(self._route_import_btn)
        io_row.addWidget(self._route_export_current_btn)
        layout.addLayout(io_row)

        self._route_export_all_btn = NeumorphicButton("导出全部")
        self._route_export_all_btn.clicked.connect(self.route_export_all_clicked.emit)
        layout.addWidget(self._route_export_all_btn)

        layout.addStretch()

    def _on_close(self):
        self.hide()
        self.closed.emit()

    def _on_route_selected(self, _index: int):
        self.route_selected_changed.emit(self.selected_route_id())

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
        self._summary_label.setText(f"共 {len(routes)} 条路线" if routes else "暂无已保存路线")

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
            text = "当前画布暂无路线"
        else:
            dirty_text = "，未保存" if dirty else ""
            editing_text = "，编辑中" if editing else ""
            text = f"当前路线: {point_count} 点，{distance:.0f}px{dirty_text}{editing_text}"
        self._route_info_label.setText(text)

    def set_route_editing_active(self, active: bool):
        self._route_draw_btn.setEnabled(not active)
        self._route_finish_btn.setEnabled(active)
        self._route_cancel_btn.setEnabled(active)
