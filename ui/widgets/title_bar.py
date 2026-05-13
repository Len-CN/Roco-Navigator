"""
自定义标题栏

无边框窗口的自定义标题栏，支持拖动移动窗口。
新拟物派设计风格。
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPen

from .neumorphic import (
    BG_SECONDARY, BG_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ERROR
)


class WindowControlButton(QPushButton):
    """绘制式窗口控制按钮，避免依赖字体符号。"""

    def __init__(self, icon_name: str, parent=None, is_close: bool = False):
        super().__init__(parent)
        self._icon_name = icon_name
        self._is_close = is_close
        self.setFixedSize(34, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: {"#fee2e2" if is_close else BG_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {"#fecaca" if is_close else "#d8dce3"};
            }}
        """)

    def set_icon_name(self, icon_name: str):
        self._icon_name = icon_name
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(ERROR if self._is_close and self.underMouse() else TEXT_PRIMARY)
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        cx = self.width() / 2
        cy = self.height() / 2
        if self._icon_name == "minimize":
            painter.drawLine(int(cx - 5), int(cy + 4), int(cx + 5), int(cy + 4))
        elif self._icon_name == "maximize":
            painter.drawRect(int(cx - 5), int(cy - 5), 10, 10)
        elif self._icon_name == "restore":
            painter.drawRect(int(cx - 3), int(cy - 6), 9, 9)
            painter.drawRect(int(cx - 6), int(cy - 3), 9, 9)
        elif self._icon_name == "close":
            painter.drawLine(int(cx - 5), int(cy - 5), int(cx + 5), int(cy + 5))
            painter.drawLine(int(cx + 5), int(cy - 5), int(cx - 5), int(cy + 5))


class TitleBar(QWidget):
    """自定义标题栏"""

    def __init__(self, parent=None, title="洛克导航"):
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
        from .neumorphic import StatusIndicator
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
        self._min_btn = self._create_control_button("minimize")
        self._max_btn = self._create_control_button("maximize")
        self._close_btn = self._create_control_button("close", is_close=True)
        self._min_btn.setToolTip("最小化")
        self._max_btn.setToolTip("最大化")
        self._close_btn.setToolTip("关闭")

        self._min_btn.clicked.connect(self._on_minimize)
        self._max_btn.clicked.connect(self._on_maximize)
        self._close_btn.clicked.connect(self._on_close)

        layout.addWidget(self._min_btn)
        layout.addWidget(self._max_btn)
        layout.addWidget(self._close_btn)

    def _create_control_button(self, icon_name, is_close=False):
        return WindowControlButton(icon_name, self, is_close=is_close)

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
                self._max_btn.set_icon_name("maximize")
                self._max_btn.setToolTip("最大化")
            else:
                self._parent_window.showMaximized()
                self._max_btn.set_icon_name("restore")
                self._max_btn.setToolTip("还原")

    def _on_close(self):
        if self._parent_window:
            self._parent_window.close()
