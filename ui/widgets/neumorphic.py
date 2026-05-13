"""
新拟物派 (Neumorphism) 基础组件

提供统一的新拟物派风格 PyQt5 控件。
核心特征: 浅色背景 + 柔和阴影 + 稳定圆角 + 中文优先字体。
"""

from PyQt5.QtWidgets import (
    QPushButton, QLineEdit, QFrame, QLabel, QSlider,
    QProgressBar, QCheckBox, QGraphicsDropShadowEffect,
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath


# ==================== 设计 Token ====================
BG_PRIMARY = "#e0e5ec"
BG_SECONDARY = "#f0f0f3"
BG_CARD = "#ecf0f3"
BG_INSET = "#d8dce3"
TEXT_PRIMARY = "#4a5568"
TEXT_SECONDARY = "#718096"
TEXT_DISABLED = "#a0aec0"
ACCENT = "#667eea"
ACCENT_LIGHT = "#7c93ed"
ACCENT_DARK = "#5a6fd6"
SUCCESS = "#48bb78"
WARNING = "#ed8936"
ERROR = "#f56565"
SHADOW_DARK = "#b8bcc2"
SHADOW_LIGHT = "#ffffff"
BORDER = "#d1d5db"
BORDER_DARK = "#c8ccd2"

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
FONT_MONO = '"Consolas", "Cascadia Mono", "Microsoft YaHei UI", monospace'

RADIUS_XS = 4
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 20

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20

FONT_SIZE_CAPTION = 12
FONT_SIZE_BODY = 13
FONT_SIZE_TITLE = 18


def font_qss(size=FONT_SIZE_BODY, weight=400, family=FONT_FAMILY):
    return f'font-family: {family}; font-size: {size}px; font-weight: {weight};'


def base_scrollbar_qss(track=BG_SECONDARY, handle=TEXT_DISABLED, width=8):
    radius = max(3, width // 2)
    return f"""
        QScrollBar:vertical {{
            background: {track};
            width: {width}px;
            border-radius: {radius}px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {handle};
            border-radius: {radius}px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {TEXT_SECONDARY};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


def checkbox_qss():
    return f"""
        QCheckBox {{
            color: {TEXT_PRIMARY};
            spacing: 8px;
            background: transparent;
            {font_qss()}
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: {RADIUS_XS}px;
            border: 1px solid {BORDER_DARK};
            background-color: {BG_PRIMARY};
        }}
        QCheckBox::indicator:hover {{
            border-color: {ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT};
            border-color: {ACCENT};
        }}
        QCheckBox::indicator:indeterminate {{
            background-color: {BG_SECONDARY};
            border-color: {ACCENT};
        }}
        QCheckBox:disabled {{
            color: {TEXT_DISABLED};
        }}
    """


def switch_qss():
    return f"""
        QCheckBox {{
            background: transparent;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 22px;
            height: 22px;
            border-radius: 11px;
            border: 1px solid {BORDER_DARK};
            background-color: {BG_INSET};
        }}
        QCheckBox::indicator:hover {{
            border-color: {ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT};
            border: 1px solid {ACCENT_DARK};
        }}
        QCheckBox::indicator:disabled {{
            background-color: {BORDER};
            border-color: {BORDER};
        }}
    """


def spinbox_qss():
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM}px;
            padding: 6px 10px;
            {font_qss()}
            min-height: 28px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {ACCENT};
            background-color: {BG_CARD};
        }}
        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            width: 18px;
            border: none;
            background: transparent;
        }}
    """


def tab_qss():
    return f"""
        QTabWidget::pane {{
            background-color: {BG_SECONDARY};
            border: none;
            border-radius: {RADIUS_MD}px;
        }}
        QTabBar::tab {{
            background-color: {BG_PRIMARY};
            color: {TEXT_SECONDARY};
            padding: 9px 16px;
            border: none;
            border-top-left-radius: {RADIUS_SM}px;
            border-top-right-radius: {RADIUS_SM}px;
            margin-right: 2px;
            {font_qss()}
        }}
        QTabBar::tab:selected {{
            background-color: {BG_SECONDARY};
            color: {TEXT_PRIMARY};
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            color: {ACCENT};
        }}
    """


def menu_qss():
    return f"""
        QMenu {{
            background-color: {BG_PRIMARY};
            color: {TEXT_PRIMARY};
            border: 1px solid {SHADOW_DARK};
            border-radius: {RADIUS_SM}px;
            padding: 4px;
            margin: 1px;
            {font_qss()}
        }}
        QMenu::item {{
            padding: 7px 22px;
            border-radius: 5px;
        }}
        QMenu::item:selected {{
            background-color: {ACCENT};
            color: #ffffff;
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDER};
            margin: 4px 8px;
        }}
    """


def prepare_rounded_popup(widget):
    """Let native popup widgets show QSS rounded corners without hard mask jaggies."""
    if not widget:
        return
    widget.setWindowFlags(
        widget.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    )
    widget.clearMask()
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    widget.setAttribute(Qt.WA_NoSystemBackground, True)
    widget.setAutoFillBackground(False)


def prepare_combo_popup_window(widget):
    """Use an opaque native combo popup to avoid transparent-window shadow artifacts."""
    if not widget:
        return
    widget.clearMask()
    widget.setAttribute(Qt.WA_TranslucentBackground, False)
    widget.setAttribute(Qt.WA_NoSystemBackground, False)
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(widget.backgroundRole(), QColor(BG_SECONDARY))
    widget.setPalette(palette)


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

    def __init__(self, text="", parent=None, primary=False, danger=False):
        super().__init__(text, parent)
        self._primary = primary
        self._danger = danger
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(42)
        self._apply_style()

    def _apply_style(self):
        if self._danger:
            bg = ERROR
            hover = "#fb7185"
            pressed = "#e53e3e"
            fg = "#ffffff"
            border = "none"
            weight = 600
        elif self._primary:
            bg = ACCENT
            hover = ACCENT_LIGHT
            pressed = ACCENT_DARK
            fg = "#ffffff"
            border = "none"
            weight = 600
        else:
            bg = BG_PRIMARY
            hover = BG_CARD
            pressed = "#d1d5db"
            fg = TEXT_PRIMARY
            border = f"1px solid {BORDER}"
            weight = 500

        disabled_bg = TEXT_DISABLED if (self._primary or self._danger) else BG_PRIMARY
        disabled_fg = BG_SECONDARY if (self._primary or self._danger) else TEXT_DISABLED

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {border};
                border-radius: {RADIUS_MD}px;
                padding: 9px 16px;
                {font_qss(FONT_SIZE_BODY, weight)}
            }}
            QPushButton:hover {{
                background-color: {hover};
                border-color: {BORDER_DARK};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
            QPushButton:focus {{
                border: 1px solid {ACCENT};
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg};
                color: {disabled_fg};
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
                background-color: {BG_INSET};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_DARK};
                border-radius: {RADIUS_MD}px;
                padding: 9px 14px;
                {font_qss()}
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
        self.setObjectName("neumorphicCard")
        self.setStyleSheet(f"""
            QFrame#neumorphicCard {{
                background-color: {BG_CARD};
                border: none;
                border-radius: {RADIUS_LG}px;
            }}
        """)
        apply_shadow(self, blur=18, offset_x=6, offset_y=6)


class NeumorphicPanel(QFrame):
    """新拟物派面板 (内凹效果)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("neumorphicPanel")
        self.setStyleSheet(f"""
            QFrame#neumorphicPanel {{
                background-color: {BG_INSET};
                border: 1px solid {BORDER_DARK};
                border-radius: {RADIUS_MD}px;
            }}
        """)


class NeumorphicLabel(QLabel):
    """新拟物派标签"""

    def __init__(self, text="", parent=None, level="body"):
        super().__init__(text, parent)

        styles = {
            "title": f"color: {TEXT_PRIMARY}; {font_qss(FONT_SIZE_TITLE, 700)}",
            "subtitle": f"color: {TEXT_PRIMARY}; {font_qss(15, 600)}",
            "body": f"color: {TEXT_PRIMARY}; {font_qss(14, 400)}",
            "caption": f"color: {TEXT_SECONDARY}; {font_qss(FONT_SIZE_CAPTION, 400)}",
            "section": f"color: {TEXT_SECONDARY}; {font_qss(12, 700)}",
        }
        self.setStyleSheet(
            f"QLabel {{ {styles.get(level, styles['body'])} background: transparent; }}"
        )


class NeumorphicSlider(QSlider):
    """新拟物派滑块"""

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background-color: {BG_INSET};
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
                background-color: {BG_INSET};
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
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: transparent;
                color: {TEXT_PRIMARY};
                border: none;
                padding: 6px 32px 6px 12px;
                {font_qss()}
            }}
            QComboBox:hover {{
                background-color: transparent;
            }}
            QComboBox:focus {{
                background-color: transparent;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: border;
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
                border-radius: 0px;
                padding: 4px;
                selection-background-color: {ACCENT};
                selection-color: #ffffff;
                outline: none;
                {font_qss()}
            }}
            QComboBox QAbstractItemView::corner {{
                background-color: {BG_SECONDARY};
                border: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                border-radius: {RADIUS_XS}px;
                min-height: 28px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {BG_CARD};
            }}
            QComboBox:disabled {{
                color: {TEXT_DISABLED};
            }}
        """)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg = QColor(BG_CARD if self.underMouse() else BG_PRIMARY)
        border = QColor(ACCENT if self.hasFocus() else BORDER)
        painter.setPen(border)
        painter.setBrush(bg)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS_SM, RADIUS_SM)

        painter.setPen(QColor(TEXT_DISABLED if not self.isEnabled() else TEXT_PRIMARY))
        text_rect = self.rect().adjusted(12, 0, -34, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.currentText())

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.clearMask()

    def showPopup(self):
        super().showPopup()
        view = self.view()
        if not view:
            return

        view.setAutoFillBackground(False)
        view.viewport().setAutoFillBackground(False)
        view.setFrameShape(QFrame.NoFrame)

        win = view.window()
        if win and win is not self:
            prepare_combo_popup_window(win)


class NeumorphicSwitch(QCheckBox):
    """统一开关控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(switch_qss())


class NeumorphicSeparator(QFrame):
    """新拟物派分隔线"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(1)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BORDER};
                border: none;
            }}
        """)


class CollapsibleSection(QWidget):
    """侧栏折叠分组"""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self._title = title
        self._expanded = expanded
        self.setObjectName("collapsibleSection")
        self.setStyleSheet(f"""
            QWidget#collapsibleSection {{
                background-color: transparent;
            }}
            QPushButton#sectionHeader {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 9px 12px;
                text-align: left;
                {font_qss(13, 600)}
            }}
            QPushButton#sectionHeader:hover {{
                background-color: {BG_PRIMARY};
                border-color: {BORDER_DARK};
            }}
            QWidget#sectionContent {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._header = QPushButton()
        self._header.setObjectName("sectionHeader")
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setMinimumHeight(38)
        self._header.clicked.connect(self.toggle)
        layout.addWidget(self._header)

        self._content = QWidget()
        self._content.setObjectName("sectionContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(2, 0, 2, 4)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content)

        self.set_expanded(expanded)

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._content.setVisible(expanded)
        marker = "▼" if expanded else "▶"
        self._header.setText(f"{marker}  {self._title}")
        self.toggled.emit(expanded)

    @property
    def is_expanded(self) -> bool:
        return self._expanded


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
