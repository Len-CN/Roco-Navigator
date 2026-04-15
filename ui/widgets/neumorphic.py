"""
新拟物派 (Neumorphism) 基础组件

提供统一的新拟物派风格 PyQt5 控件。
核心特征: 浅色背景 + 双重阴影 + 圆角 + 柔和配色
"""

from PyQt5.QtWidgets import (
    QPushButton, QLineEdit, QFrame, QLabel, QSlider,
    QProgressBar, QCheckBox, QGraphicsDropShadowEffect,
    QWidget, QVBoxLayout, QHBoxLayout
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
                    padding: 12px 24px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {ACCENT_LIGHT};
                }}
                QPushButton:pressed {{
                    background-color: #5a6fd6;
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
                    border: none;
                    border-radius: 12px;
                    padding: 12px 24px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {BG_CARD};
                }}
                QPushButton:pressed {{
                    background-color: #d1d5db;
                }}
                QPushButton:disabled {{
                    color: {TEXT_DISABLED};
                }}
            """)
        apply_shadow(self, blur=12, offset_x=4, offset_y=4)


class NeumorphicInput(QLineEdit):
    """新拟物派输入框"""

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(40)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                font-size: 14px;
                selection-background-color: {ACCENT};
                selection-color: #ffffff;
            }}
            QLineEdit:focus {{
                background-color: {BG_CARD};
            }}
            QLineEdit:disabled {{
                color: {TEXT_DISABLED};
            }}
        """)
        # 内凹阴影效果 (用深色阴影模拟)
        apply_shadow(self, blur=8, offset_x=2, offset_y=2, color="#c8ccd2")


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
                border: none;
                border-radius: 12px;
            }}
        """)
        apply_shadow(self, blur=8, offset_x=2, offset_y=2, color="#c0c4ca")


class NeumorphicLabel(QLabel):
    """新拟物派标签"""

    def __init__(self, text="", parent=None, level="body"):
        super().__init__(text, parent)
        
        styles = {
            "title": f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;",
            "subtitle": f"color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 600;",
            "body": f"color: {TEXT_PRIMARY}; font-size: 14px;",
            "caption": f"color: {TEXT_SECONDARY}; font-size: 12px;",
            "section": f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600; letter-spacing: 1px;",
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
