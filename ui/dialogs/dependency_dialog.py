"""
依赖管理对话框 - 简洁版

使用官方源，支持断点续传，无镜像站
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ...utils.package_manager import PackageManager
from ..widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicProgress,
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT, SUCCESS, ERROR, SHADOW_DARK, BORDER, FONT_FAMILY,
    FONT_MONO, font_qss, base_scrollbar_qss
)


class InstallThread(QThread):
    """安装线程"""

    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, manager: PackageManager, feature_key: str):
        super().__init__()
        self.manager = manager
        self.feature_key = feature_key

    def run(self):
        """执行功能安装"""
        try:
            success, log = self.manager.install_feature(
                self.feature_key,
                lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(success, log)
        except Exception as e:
            self.finished.emit(False, str(e))


class DependencyDialog(QDialog):
    """依赖管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("功能管理")
        self.setMinimumSize(700, 600)

        self.manager = PackageManager()
        self.install_thread = None

        self._init_ui()
        self._refresh_status()
    
    def _init_ui(self):
        """初始化 UI"""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_PRIMARY};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = NeumorphicLabel("功能管理", level="title")
        layout.addWidget(title)

        # 说明
        desc = NeumorphicLabel(
            "安装可选功能以增强程序能力。\n"
            "所有文件从官方源下载，安全可靠。",
            level="caption",
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 功能列表
        list_label = NeumorphicLabel("可选功能：", level="body")
        layout.addWidget(list_label)
        
        self.package_list = QListWidget()
        self.package_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 5px;
                {font_qss()}
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {BG_PRIMARY};
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
            }}
            {base_scrollbar_qss(BG_SECONDARY, SHADOW_DARK, 8)}
        """)
        layout.addWidget(self.package_list)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.install_btn = NeumorphicButton("安装选中", primary=True)
        self.install_btn.clicked.connect(self._on_install)
        btn_layout.addWidget(self.install_btn)
        
        self.uninstall_btn = NeumorphicButton("卸载选中")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        btn_layout.addWidget(self.uninstall_btn)
        
        self.refresh_btn = NeumorphicButton("刷新状态")
        self.refresh_btn.clicked.connect(self._refresh_status)
        btn_layout.addWidget(self.refresh_btn)
        
        btn_layout.addStretch()
        
        self.close_btn = NeumorphicButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
        # 进度条
        self.progress_bar = NeumorphicProgress()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 日志区
        log_label = NeumorphicLabel("操作日志：", level="body")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #2b2b2b;
                color: #f0f0f0;
                border: none;
                border-radius: 12px;
                padding: 8px;
                font-family: {FONT_MONO};
                font-size: 10px;
            }}
            {base_scrollbar_qss("#2b2b2b", "#666666", 8)}
        """)
        layout.addWidget(self.log_text)
    
    def _refresh_status(self):
        """刷新功能状态"""
        self.package_list.clear()

        for feat_key, feat in self.manager.FEATURES.items():
            installed = self.manager.check_feature_installed(feat_key)

            status = "✓ 已启用" if installed else "○ 未安装"
            size = feat["total_size_mb"]
            size_str = f"约 {size / 1024:.1f} GB" if size >= 1024 else f"约 {size} MB"

            text = f"{status}  {feat['feature_name']}  ({size_str}) — {feat['description']}"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, feat_key)

            if installed:
                item.setForeground(Qt.darkGreen)
            else:
                item.setForeground(Qt.darkGray)

            self.package_list.addItem(item)

        self._log("状态已刷新")
    
    def _log(self, message: str):
        """添加日志"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _on_install(self):
        """安装选中的功能"""
        item = self.package_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择要安装的功能")
            return

        feature_key = item.data(Qt.UserRole)
        feat = self.manager.FEATURES.get(feature_key)
        if not feat:
            return

        if self.manager.check_feature_installed(feature_key):
            QMessageBox.information(self, "提示", "该功能已安装")
            return

        # 检查前置依赖
        depends_on = feat.get("depends_on")
        if depends_on and not self.manager.check_feature_installed(depends_on):
            dep_name = self.manager.FEATURES[depends_on]["feature_name"]
            QMessageBox.warning(
                self, "提示",
                f"请先安装「{dep_name}」",
            )
            return

        size = feat["total_size_mb"]
        size_str = f"{size / 1024:.1f} GB" if size >= 1024 else f"{size} MB"

        reply = QMessageBox.question(
            self,
            "确认安装",
            f"确定要安装「{feat['feature_name']}」吗？\n\n"
            f"{feat['description']}\n"
            f"预计大小: {size_str}\n"
            f"将从官方源下载。",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self._start_installation(feature_key)
    
    def _start_installation(self, feature_key: str):
        """开始安装功能"""
        if hasattr(self, 'install_thread') and self.install_thread and self.install_thread.isRunning():
            return
        self.install_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        feat = self.manager.FEATURES[feature_key]
        self._log(f"\n开始安装「{feat['feature_name']}」...")

        self.install_thread = InstallThread(self.manager, feature_key)
        self.install_thread.progress.connect(self._on_progress)
        self.install_thread.finished.connect(self._on_install_finished)
        self.install_thread.start()
    
    def _on_progress(self, message: str):
        """安装进度"""
        self._log(message)
    
    def _on_install_finished(self, success: bool, log: str):
        """安装完成"""
        self.progress_bar.setVisible(False)

        self.install_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)

        if success:
            self._log("\n✓ 安装成功！")

            item = self.package_list.currentItem()
            if item:
                feature_key = item.data(Qt.UserRole)
                feat = self.manager.FEATURES.get(feature_key, {})
                if feat.get("restart_required"):
                    QMessageBox.information(
                        self, "安装成功",
                        f"「{feat['feature_name']}」安装完成！\n\n"
                        "请重启程序以启用新功能。\n"
                        "关闭程序后重新运行 start.bat 即可。",
                    )
                else:
                    QMessageBox.information(self, "成功", "安装完成！")
            else:
                QMessageBox.information(self, "成功", "安装完成！")
        else:
            self._log(f"\n✗ 安装失败\n{log}")
            QMessageBox.critical(self, "失败", f"安装失败：\n{log[:200]}")

        self._refresh_status()
    
    def _on_uninstall(self):
        """卸载选中的功能"""
        item = self.package_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择要卸载的功能")
            return

        feature_key = item.data(Qt.UserRole)
        feat = self.manager.FEATURES.get(feature_key)
        if not feat:
            return

        if not self.manager.check_feature_installed(feature_key):
            QMessageBox.information(self, "提示", "该功能未安装")
            return

        reply = QMessageBox.question(
            self,
            "确认卸载",
            f"确定要卸载「{feat['feature_name']}」吗？",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self._log(f"\n卸载「{feat['feature_name']}」...")
        self.install_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)

        from PyQt5.QtCore import QThread, pyqtSignal

        class _UninstallThread(QThread):
            finished = pyqtSignal(bool, str)
            log_msg = pyqtSignal(str)

            def __init__(self, manager, feature_key):
                super().__init__()
                self._manager = manager
                self._feature_key = feature_key

            def run(self):
                success, log = self._manager.uninstall_feature(
                    self._feature_key, lambda msg: self.log_msg.emit(msg))
                self.finished.emit(success, log)

        def _on_uninstall_done(success, log):
            self.install_btn.setEnabled(True)
            self.uninstall_btn.setEnabled(True)
            if success:
                self._log("✓ 卸载成功")
                QMessageBox.information(self, "成功", "卸载完成！")
            else:
                self._log(f"✗ 卸载失败\n{log}")
                QMessageBox.critical(self, "失败", f"卸载失败：\n{log[:200]}")
            self._refresh_status()

        self._uninstall_thread = _UninstallThread(self.manager, feature_key)
        self._uninstall_thread.log_msg.connect(self._log)
        self._uninstall_thread.finished.connect(_on_uninstall_done)
        self._uninstall_thread.start()
