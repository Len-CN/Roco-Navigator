"""
自定义标题栏

无边框窗口的自定义标题栏，支持拖动移动窗口。
新拟物派设计风格。
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QColor, QFont, QMouseEvent

from roco_navigator.ui.widgets.neumorphic import (
    BG_SECONDARY, BG_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT, ERROR, apply_shadow
)


class TitleBar(QWidget):
    """自定义标题栏"""

    def __init__(self, parent=None, title="Roco Navigator"):
        super().__init__(parent)
        self._parent_window = parent
        self._dragging = False
        self._drag_start = QPoint()

        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SECONDARY};
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom: none;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)

        # 应用图标/状态指示
        from roco_navigator.ui.widgets.neumorphic import StatusIndicator
        self._status = StatusIndicator()
        self._status.set_status("idle")
        layout.addWidget(self._status)

        # 标题文字
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        layout.addWidget(self._title_label)

        layout.addStretch()

        # 状态文字 (如 "追踪中", "导航中")
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                background: transparent;
            }}
        """)
        layout.addWidget(self._status_label)

        # 窗口控制按钮
        self._min_btn = self._create_control_button("\u2212")  # minus sign
        self._max_btn = self._create_control_button("\u25a1")  # square
        self._close_btn = self._create_control_button("\u00d7", is_close=True)  # ×

        self._min_btn.clicked.connect(self._on_minimize)
        self._max_btn.clicked.connect(self._on_maximize)
        self._close_btn.clicked.connect(self._on_close)

        layout.addWidget(self._min_btn)
        layout.addWidget(self._max_btn)
        layout.addWidget(self._close_btn)

    def _create_control_button(self, text, is_close=False):
        btn = QPushButton(text)
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.PointingHandCursor)
        
        hover_bg = "#fecaca" if is_close else BG_PRIMARY
        hover_color = ERROR if is_close else TEXT_PRIMARY
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: 16px;
                font-size: 16px;
                font-weight: 400;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_color};
            }}
        """)
        return btn

    def set_status_text(self, text: str):
        self._status_label.setText(text)

    def set_status(self, status: str):
        self._status.set_status(status)

    def set_title(self, title: str):
        self._title_label.setText(title)

    # ---- Window dragging ----
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.globalPos() - self._parent_window.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and self._parent_window:
            self._parent_window.move(event.globalPos() - self._drag_start)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._on_maximize()

    # ---- Window controls ----
    def _on_minimize(self):
        if self._parent_window:
            self._parent_window.showMinimized()

    def _on_maximize(self):
        if self._parent_window:
            if self._parent_window.isMaximized():
                self._parent_window.showNormal()
                self._max_btn.setText("\u25a1")
            else:
                self._parent_window.showMaximized()
                self._max_btn.setText("\u25a3")

    def _on_close(self):
        if self._parent_window:
            self._parent_window.close()
