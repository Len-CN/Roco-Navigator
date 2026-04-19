"""
依赖管理对话框 - 简洁版

使用官方源，支持断点续传，无镜像站
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QProgressBar, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from ...utils.package_manager import PackageManager
from ..widgets.neumorphic import (
    NeumorphicButton, NeumorphicCard, NeumorphicLabel,
    NeumorphicProgress,
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT, SUCCESS, ERROR, SHADOW_DARK
)


class InstallThread(QThread):
    """安装线程"""
    
    progress = pyqtSignal(str)  # 进度消息
    finished = pyqtSignal(bool, str)  # 完成信号 (成功, 消息)
    
    def __init__(self, manager: PackageManager, package_key: str):
        super().__init__()
        self.manager = manager
        self.package_key = package_key
    
    def run(self):
        """执行安装"""
        try:
            success, log = self.manager.install_package(
                self.package_key,
                lambda msg: self.progress.emit(msg)
            )
            self.finished.emit(success, log)
        except Exception as e:
            self.finished.emit(False, str(e))


class DependencyDialog(QDialog):
    """依赖管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("依赖管理")
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
        title = NeumorphicLabel("依赖管理", level="title")
        layout.addWidget(title)
        
        # 说明
        desc = NeumorphicLabel(
            "管理程序依赖包。大文件支持断点续传，可随时暂停。\n"
            "使用官方源下载，确保安全可靠。",
            level="caption"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 包列表
        list_label = NeumorphicLabel("可用包：", level="body")
        layout.addWidget(list_label)
        
        self.package_list = QListWidget()
        self.package_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {BG_SECONDARY};
                border: none;
                border-radius: 12px;
                padding: 5px;
                font-family: "Microsoft YaHei", sans-serif;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {BG_PRIMARY};
            }}
            QListWidget::item:selected {{
                background-color: {BG_PRIMARY};
                color: {TEXT_PRIMARY};
            }}
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
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }}
        """)
        layout.addWidget(self.log_text)
    
    def _refresh_status(self):
        """刷新包状态"""
        self.package_list.clear()
        
        for key, config in self.manager.PACKAGES.items():
            installed = self.manager.check_installed(key)
            
            # 创建列表项
            display_name = config["display_name"]
            size_mb = config["size_mb"]
            required = config.get("required", False)
            
            status = "✓ 已安装" if installed else "○ 未安装"
            tag = "[必需]" if required else "[可选]"
            
            text = f"{status}  {display_name}  ({size_mb} MB)  {tag}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            
            # 设置颜色
            if installed:
                item.setForeground(Qt.darkGreen)
            elif required:
                item.setForeground(Qt.red)
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
        """安装选中的包"""
        item = self.package_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择要安装的包")
            return
        
        package_key = item.data(Qt.UserRole)
        config = self.manager.PACKAGES[package_key]
        
        # 检查是否已安装
        if self.manager.check_installed(package_key):
            QMessageBox.information(self, "提示", "该包已安装")
            return
        
        # 确认安装
        reply = QMessageBox.question(
            self,
            "确认安装",
            f"确定要安装 {config['display_name']} ({config['size_mb']} MB) 吗？\n\n"
            f"将从官方源下载，支持断点续传。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 开始安装
        self._start_installation(package_key)
    
    def _start_installation(self, package_key: str):
        """开始安装"""
        self.install_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定模式
        
        config = self.manager.PACKAGES[package_key]
        self._log(f"\n开始安装 {config['display_name']}...")
        
        # 创建安装线程
        self.install_thread = InstallThread(self.manager, package_key)
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
            
            # 检查是否安装了需要重启的包
            item = self.package_list.currentItem()
            if item:
                package_key = item.data(Qt.UserRole)
                if package_key in ["torch", "kornia"]:
                    QMessageBox.information(
                        self, "安装成功",
                        "安装完成！\n\n"
                        "请重启程序以使用 AI 功能。\n"
                        "关闭程序后重新运行 start.bat 即可。"
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
        """卸载选中的包"""
        item = self.package_list.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择要卸载的包")
            return
        
        package_key = item.data(Qt.UserRole)
        config = self.manager.PACKAGES[package_key]
        
        # 检查是否已安装
        if not self.manager.check_installed(package_key):
            QMessageBox.information(self, "提示", "该包未安装")
            return
        
        # 确认卸载
        reply = QMessageBox.question(
            self,
            "确认卸载",
            f"确定要卸载 {config['display_name']} 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 执行卸载
        self._log(f"\n卸载 {config['display_name']}...")
        success, log = self.manager.uninstall_package(config["name"])
        
        if success:
            self._log("✓ 卸载成功")
            QMessageBox.information(self, "成功", "卸载完成！")
        else:
            self._log(f"✗ 卸载失败\n{log}")
            QMessageBox.critical(self, "失败", f"卸载失败：\n{log[:200]}")
        
        self._refresh_status()
