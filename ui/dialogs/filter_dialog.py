"""
点位筛选对话框

bwiki 同款分类，支持多选，过滤无效（0点位）的分类。
"""

import logging
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QScrollArea, QWidget,
    QFrame, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from .frameless_dialog import FramelessRoundedDialog
from ..widgets.neumorphic import (
    NeumorphicButton, NeumorphicLabel, NeumorphicSeparator,
    BG_PRIMARY, BG_SECONDARY, BG_CARD, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_DISABLED, ACCENT, SUCCESS,
    checkbox_qss, base_scrollbar_qss, FONT_FAMILY, font_qss
)

logger = logging.getLogger(__name__)


class FilterDialog(FramelessRoundedDialog):
    """点位筛选对话框"""

    filter_applied = pyqtSignal(object)  # emits set of selected mark_type_names

    def __init__(self, grouped_data: dict, point_counts: dict,
                 current_selection: set, parent=None):
        """
        Args:
            grouped_data: {type_name: [mark_type_name, ...], ...}
            point_counts: {mark_type_name: point_count, ...}
            current_selection: currently selected mark_type_names
            parent: parent widget
        """
        super().__init__(BG_SECONDARY, parent=parent)
        self.setWindowTitle("点位筛选")
        self.setFixedSize(500, 600)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: transparent;
            }}
        """)

        self._grouped_data = grouped_data
        self._point_counts = point_counts
        self._current_selection = set(current_selection) if current_selection else set()
        self._updating_checkboxes = False

        # State: category checkboxes and sub-item checkboxes
        self._category_checkboxes = {}   # {type_name: QCheckBox}
        self._sub_checkboxes = {}        # {mark_type_name: QCheckBox}
        self._category_subs = {}         # {type_name: [mark_type_name, ...]}

        self._build_ui()
        self._restore_selection()

    def _make_font(self, bold=False, size=13):
        font = QFont("Microsoft YaHei UI", size)
        font.setBold(bold)
        return font

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = NeumorphicLabel("点位筛选", level="title")
        layout.addWidget(title)

        # Top buttons: select all / deselect all
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self._select_all_btn = NeumorphicButton("全选", primary=True)
        self._select_all_btn.clicked.connect(self._on_select_all)
        self._deselect_all_btn = NeumorphicButton("取消全选")
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)
        top_row.addWidget(self._select_all_btn)
        top_row.addWidget(self._deselect_all_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Scroll area for categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_PRIMARY};
                border: none;
                border-radius: 8px;
            }}
            {base_scrollbar_qss(BG_PRIMARY, TEXT_DISABLED, 6)}
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background-color: {BG_PRIMARY}; border-radius: 8px;")
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(10, 10, 10, 10)
        self._scroll_layout.setSpacing(8)

        checkbox_style = checkbox_qss()

        for type_name, sub_names in self._grouped_data.items():
            # Filter sub-items to only those with count > 0
            valid_subs = [s for s in sub_names if self._point_counts.get(s, 0) > 0]
            if not valid_subs:
                continue

            # Category total count
            cat_total = sum(self._point_counts.get(s, 0) for s in valid_subs)

            # Category header checkbox
            cat_cb = QCheckBox(f"{type_name} ({cat_total})")
            cat_cb.setTristate(True)
            cat_cb.setStyleSheet(checkbox_style)
            cat_cb.setFont(self._make_font(bold=True, size=13))
            cat_cb.stateChanged.connect(
                lambda state, tn=type_name: self._on_category_toggled(tn, state)
            )
            self._scroll_layout.addWidget(cat_cb)
            self._category_checkboxes[type_name] = cat_cb
            self._category_subs[type_name] = list(valid_subs)

            # Sub-items in grid layout (2 columns)
            grid = QGridLayout()
            grid.setContentsMargins(20, 0, 0, 4)
            grid.setSpacing(4)
            for idx, sub_name in enumerate(valid_subs):
                count = self._point_counts.get(sub_name, 0)
                sub_cb = QCheckBox(f"{sub_name} ({count})")
                sub_cb.setStyleSheet(checkbox_style)
                sub_cb.setFont(self._make_font(bold=False, size=13))
                sub_cb.stateChanged.connect(self._on_sub_toggled)
                row = idx // 2
                col = idx % 2
                grid.addWidget(sub_cb, row, col)
                self._sub_checkboxes[sub_name] = sub_cb

            self._scroll_layout.addLayout(grid)

        self._scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Bottom buttons
        layout.addWidget(NeumorphicSeparator())
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addStretch()
        self._cancel_btn = NeumorphicButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        self._ok_btn = NeumorphicButton("确定", primary=True)
        self._ok_btn.clicked.connect(self._on_ok)
        bottom_row.addWidget(self._cancel_btn)
        bottom_row.addWidget(self._ok_btn)
        layout.addLayout(bottom_row)

    def _restore_selection(self):
        """Restore checkbox states from current_selection."""
        if not self._current_selection:
            return

        self._updating_checkboxes = True
        for name, cb in self._sub_checkboxes.items():
            cb.setChecked(name in self._current_selection)

        # Update category states
        for type_name, sub_names in self._category_subs.items():
            if not sub_names:
                continue
            checked_count = sum(
                1 for sn in sub_names
                if self._sub_checkboxes.get(sn) and self._sub_checkboxes[sn].isChecked()
            )
            cat_cb = self._category_checkboxes.get(type_name)
            if cat_cb:
                if checked_count == 0:
                    cat_cb.setCheckState(Qt.Unchecked)
                elif checked_count == len(sub_names):
                    cat_cb.setCheckState(Qt.Checked)
                else:
                    cat_cb.setCheckState(Qt.PartiallyChecked)
        self._updating_checkboxes = False

    def _on_category_toggled(self, type_name: str, state: int):
        if self._updating_checkboxes:
            return
        self._updating_checkboxes = True
        checked = (state == Qt.Checked)
        for sub_name in self._category_subs.get(type_name, []):
            cb = self._sub_checkboxes.get(sub_name)
            if cb:
                cb.setChecked(checked)
        self._updating_checkboxes = False

    def _on_sub_toggled(self, _state: int):
        if self._updating_checkboxes:
            return
        self._updating_checkboxes = True
        for type_name, sub_names in self._category_subs.items():
            if not sub_names:
                continue
            checked_count = sum(
                1 for sn in sub_names
                if self._sub_checkboxes.get(sn) and self._sub_checkboxes[sn].isChecked()
            )
            cat_cb = self._category_checkboxes.get(type_name)
            if cat_cb:
                if checked_count == 0:
                    cat_cb.setCheckState(Qt.Unchecked)
                elif checked_count == len(sub_names):
                    cat_cb.setCheckState(Qt.Checked)
                else:
                    cat_cb.setCheckState(Qt.PartiallyChecked)
        self._updating_checkboxes = False

    def _on_select_all(self):
        self._updating_checkboxes = True
        for cb in self._sub_checkboxes.values():
            cb.setChecked(True)
        for cb in self._category_checkboxes.values():
            cb.setCheckState(Qt.Checked)
        self._updating_checkboxes = False

    def _on_deselect_all(self):
        self._updating_checkboxes = True
        for cb in self._sub_checkboxes.values():
            cb.setChecked(False)
        for cb in self._category_checkboxes.values():
            cb.setCheckState(Qt.Unchecked)
        self._updating_checkboxes = False

    def _get_selected(self) -> set:
        selected = set()
        for name, cb in self._sub_checkboxes.items():
            if cb.isChecked():
                selected.add(name)
        return selected

    def _on_ok(self):
        selected = self._get_selected()
        self.filter_applied.emit(selected)
        self.accept()
