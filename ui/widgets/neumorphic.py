"""
新拟物派 (Neumorphism) 基础组件

提供统一的新拟物派风格 PyQt5 控件。
核心特征: 浅色背景 + 双重阴影 + 圆角 + 柔和配色
"""

from PyQt5.QtWidgets import (
    QPushButton, QLineEdit, QFrame, QLabel, QSlider,
    QProgressBar, QCheckBox, QGraphicsDropShadowEffect,
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QLinearGradient


# ==================== 色彩常量 ====================
BG_PRIMARY = "#e0e5ec"
BG_SECONDARY = "#f0f0f3"
BG_CARD = "#ecf0f3"
TEXT_PRIMARY = "#4a5568"
TEXT_SECONDARY = "#718096"
TEXT_DISABLED = "#a0aec0"
ACCENT = "#667eea"
ACCENT_LIGHT = "#7c93ed"
SUCCESS = "#48bb78"
WARNING = "#ed8936"
ERROR = "#f56565"
SHADOW_DARK = "#b8bcc2"
SHADOW_LIGHT = "#ffffff"


def apply_shadow(widget, blur=16, offset_x=6, offset_y=6, color=SHADOW_DARK):
    """为控件应用阴影效果"""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(color))
    shadow.setOffset(offset_x, offset_y)
    widget.setGraphicsEffect(shadow)
    return shadow


class NeumorphicButton(QPushButton):
    """新拟物派按钮"""

    def __init__(self, text="", parent=None, primary=False):
        super().__init__(text, parent)
        self._primary = primary
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self._apply_style()

    def _apply_style(self):
        if self._primary:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ACCENT};
                    color: #ffffff;
                    border: none;
                    border-radius: 12px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 600;
                    font-family: "Microsoft YaHei", sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {ACCENT_LIGHT};
                }}
                QPushButton:pressed {{
                    background-color: #5a6fd6;
                    padding-left: 22px;
                    padding-top: 12px;
                }}
                QPushButton:disabled {{
                    background-color: {TEXT_DISABLED};
                    color: {BG_SECONDARY};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BG_PRIMARY};
                    color: {TEXT_PRIMARY};
                    border: 1px solid #d1d5db;
                    border-radius: 12px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                    font-family: "Microsoft YaHei", sans-serif;
                }}
                QPushButton:hover {{
                    background-color: {BG_CARD};
                    border-color: #c0c4ca;
                }}
                QPushButton:pressed {{
                    background-color: #d1d5db;
                    padding-left: 22px;
                    padding-top: 12px;
                }}
                QPushButton:disabled {{
                    color: {TEXT_DISABLED};
                    border-color: #e2e6ea;
                }}
            """)


class NeumorphicInput(QLineEdit):
    """新拟物派输入框"""

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(40)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: #d8dce3;
                color: {TEXT_PRIMARY};
                border: 1px solid #c8ccd2;
                border-radius: 12px;
                padding: 10px 16px;
                font-size: 13px;
                font-family: "Microsoft YaHei", sans-serif;
                selection-background-color: {ACCENT};
                selection-color: #ffffff;
            }}
            QLineEdit:focus {{
                background-color: {BG_CARD};
                border-color: {ACCENT};
            }}
            QLineEdit:disabled {{
                color: {TEXT_DISABLED};
            }}
        """)


class NeumorphicCard(QFrame):
    """新拟物派卡片容器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: none;
                border-radius: 16px;
            }}
        """)
        apply_shadow(self, blur=20, offset_x=8, offset_y=8)


class NeumorphicPanel(QFrame):
    """新拟物派面板 (内凹效果)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #d8dce3;
                border: 1px solid #c8ccd2;
                border-radius: 12px;
            }}
        """)


class NeumorphicLabel(QLabel):
    """新拟物派标签"""

    def __init__(self, text="", parent=None, level="body"):
        super().__init__(text, parent)
        
        styles = {
            "title": f'color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; font-family: "Microsoft YaHei", sans-serif;',
            "subtitle": f'color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 600; font-family: "Microsoft YaHei", sans-serif;',
            "body": f'color: {TEXT_PRIMARY}; font-size: 14px; font-family: "Microsoft YaHei", sans-serif;',
            "caption": f'color: {TEXT_SECONDARY}; font-size: 12px; font-family: "Microsoft YaHei", sans-serif;',
            "section": f'color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600; letter-spacing: 1px; font-family: "Microsoft YaHei", sans-serif;',
        }
        self.setStyleSheet(f"QLabel {{ {styles.get(level, styles['body'])} background: transparent; }}")


class NeumorphicSlider(QSlider):
    """新拟物派滑块"""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background-color: #d8dce3;
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background-color: {ACCENT};
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -6px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {ACCENT_LIGHT};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {ACCENT};
                border-radius: 4px;
            }}
        """)


class NeumorphicProgress(QProgressBar):
    """新拟物派进度条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.setStyleSheet(f"""
            QProgressBar {{
                background-color: #d8dce3;
                border: none;
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT};
                border-radius: 6px;
            }}
        """)


class NeumorphicComboBox(QComboBox):
    """新拟物派下拉框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self._popup_styled = False
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
                border: 1px solid #d1d5db;
                border-radius: 10px;
                padding: 6px 32px 6px 14px;
                font-size: 13px;
                font-family: "Microsoft YaHei", sans-serif;
            }}
            QComboBox:hover {{
                background-color: {BG_CARD};
                border-color: #c0c4ca;
            }}
            QComboBox:focus {{
                border-color: {ACCENT};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 28px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                width: 0;
                height: 0;
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {SHADOW_DARK};
                border-radius: 8px;
                padding: 4px;
                selection-background-color: {ACCENT};
                selection-color: #ffffff;
                outline: none;
                font-size: 13px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                border-radius: 4px;
                min-height: 28px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {BG_CARD};
            }}
            QComboBox:disabled {{
                color: {TEXT_DISABLED};
                border-color: #e2e6ea;
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        arrow_x = self.width() - 20
        arrow_y = self.height() // 2 - 2
        color = QColor(ACCENT) if self.hasFocus() else QColor(TEXT_SECONDARY)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        triangle = QPainterPath()
        triangle.moveTo(arrow_x - 4, arrow_y)
        triangle.lineTo(arrow_x + 4, arrow_y)
        triangle.lineTo(arrow_x, arrow_y + 5)
        triangle.closeSubpath()
        painter.drawPath(triangle)

    def showPopup(self):
        super().showPopup()
        # Style the popup for rounded corners (only need to do once)
        if not self._popup_styled:
            view = self.view()
            if view:
                win = view.window()
                if win and win is not self:
                    win.setWindowFlags(
                        win.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
                    )
                    win.setAttribute(Qt.WA_TranslucentBackground, True)
                    self._popup_styled = True
                    # Re-show after flag changes (flags change destroys window)
                    super().showPopup()


class NeumorphicSeparator(QFrame):
    """新拟物派分隔线"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(2)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: none;
                border-top: 1px solid {SHADOW_DARK};
                border-bottom: 1px solid {SHADOW_LIGHT};
            }}
        """)


class StatusIndicator(QWidget):
    """状态指示器 (小圆点)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = TEXT_DISABLED
        self._status = "idle"

    def set_status(self, status: str):
        """设置状态: idle, active, warning, error"""
        status_colors = {
            "idle": TEXT_DISABLED,
            "active": SUCCESS,
            "warning": WARNING,
            "error": ERROR,
            "tracking": ACCENT,
        }
        self._status = status
        self._color = status_colors.get(status, TEXT_DISABLED)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 10, 10)
