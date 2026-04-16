"""
依赖管理器 - 重新设计版

使用官方源 + 本地缓存 + 智能重试机制
"""

import sys
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple, Optional, Callable
import json
import hashlib
import time
import logging

logger = logging.getLogger(__name__)


class PackageManager:
    """包管理器"""
    
    # 包配置（仅 CPU 版本）
    PACKAGES = {
        "opencv": {
            "name": "opencv-python",
            "display_name": "OpenCV",
            "size_mb": 40,
            "required": True,
            "install_method": "pip"
        },
        "torch": {
            "name": "torch",
            "display_name": "PyTorch",
            "size_mb": 200,
            "required": False,
            "install_method": "pip",
            "index_url": "https://download.pytorch.org/whl/cpu"
        },
        "kornia": {
            "name": "kornia",
            "display_name": "Kornia",
            "size_mb": 50,
            "required": False,
            "install_method": "pip"
        },
        "ortools": {
            "name": "ortools",
            "display_name": "OR-Tools",
            "size_mb": 30,
            "required": False,
            "install_method": "pip"
        }
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        初始化包管理器
        
        Args:
            cache_dir: 缓存目录，默认为 downloads
        """
        self.python_exe = sys.executable
        
        if cache_dir is None:
            project_root = Path(__file__).parent
            cache_dir = project_root / "downloads"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 缓存元数据文件
        self.cache_meta = self.cache_dir / "cache_meta.json"
        self.meta_data = self._load_meta()
    
    def _load_meta(self) -> dict:
        """加载缓存元数据"""
        if self.cache_meta.exists():
            try:
                with open(self.cache_meta, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_meta(self):
        """保存缓存元数据"""
        try:
            with open(self.cache_meta, 'w') as f:
                json.dump(self.meta_data, f, indent=2)
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
    
    def check_installed(self, package_key: str) -> bool:
        """检查包是否已安装"""
        config = self.PACKAGES.get(package_key)
        if not config:
            return False
        
        package_name = config["name"]
        
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "show", package_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False
    
    def get_installed_packages(self) -> List[str]:
        """获取已安装的包列表"""
        installed = []
        for key in self.PACKAGES:
            if self.check_installed(key):
                installed.append(key)
        return installed
    
    def get_missing_packages(self, required_only: bool = False) -> List[str]:
        """获取缺失的包列表"""
        missing = []
        for key, config in self.PACKAGES.items():
            if required_only and not config.get("required", False):
                continue
            if not self.check_installed(key):
                missing.append(key)
        return missing
    
    def uninstall_package(self, package_name: str) -> Tuple[bool, str]:
        """卸载包"""
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "uninstall", package_name, "-y"],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)
    
    def install_package(self, package_key: str,
                       progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        安装包
        
        Args:
            package_key: 包键名
            progress_callback: 进度回调 (message: str)
        
        Returns:
            (成功, 日志)
        """
        config = self.PACKAGES.get(package_key)
        if not config:
            return False, f"未知的包: {package_key}"
        
        install_method = config.get("install_method", "pip")
        
        # 处理冲突包
        if "conflicts" in config:
            for conflict in config["conflicts"]:
                if progress_callback:
                    progress_callback(f"卸载冲突包: {conflict}")
                self.uninstall_package(conflict)
        
        # 根据安装方法选择策略
        if install_method == "pip":
            return self._install_via_pip(config, progress_callback)
        elif install_method == "wheel":
            return self._install_via_wheel(config, progress_callback)
        else:
            return False, f"不支持的安装方法: {install_method}"
    
    def _install_via_pip(self, config: dict,
                        progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """通过 pip 直接安装"""
        package_name = config["name"]
        
        if progress_callback:
            progress_callback(f"正在安装 {package_name}...")
        
        cmd = [self.python_exe, "-m", "pip", "install", package_name, "--no-cache-dir"]
        
        # 添加 index-url（如果有）
        if "index_url" in config:
            cmd.extend(["--index-url", config["index_url"]])
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            output_lines = []
            for line in process.stdout:
                output_lines.append(line)
                if progress_callback:
                    progress_callback(line.strip())
            
            process.wait()
            output = "".join(output_lines)
            
            return process.returncode == 0, output
            
        except Exception as e:
            return False, str(e)
    
    def _install_via_wheel(self, config: dict,
                          progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """通过下载 wheel 文件安装"""
        url = config.get("url")
        if not url:
            return False, "缺少 wheel URL"
        
        # 生成缓存文件名
        filename = url.split("/")[-1]
        cache_file = self.cache_dir / filename
        
        # 检查缓存
        if cache_file.exists():
            if progress_callback:
                progress_callback(f"使用缓存文件: {filename}")
        else:
            # 下载文件
            if progress_callback:
                progress_callback(f"开始下载: {filename}")
            
            success = self._download_file(url, cache_file, progress_callback)
            if not success:
                return False, "下载失败"
        
        # 安装 wheel 文件
        if progress_callback:
            progress_callback(f"正在安装 {filename}...")
        
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "install", str(cache_file), "--no-deps"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                # 安装依赖
                if progress_callback:
                    progress_callback("安装依赖包...")
                
                deps = self._get_package_dependencies(config["name"])
                for dep in deps:
                    subprocess.run(
                        [self.python_exe, "-m", "pip", "install", dep],
                        capture_output=True,
                        timeout=120
                    )
            
            return result.returncode == 0, result.stdout + result.stderr
            
        except Exception as e:
            return False, str(e)
    
    def _download_file(self, url: str, filepath: Path,
                      progress_callback: Optional[Callable] = None) -> bool:
        """
        下载文件（支持断点续传）
        
        Args:
            url: 下载 URL
            filepath: 保存路径
            progress_callback: 进度回调
        
        Returns:
            是否成功
        """
        temp_file = filepath.with_suffix(filepath.suffix + ".tmp")
        
        try:
            # 检查已下载大小
            resume_pos = 0
            if temp_file.exists():
                resume_pos = temp_file.stat().st_size
                if progress_callback:
                    progress_callback(f"继续下载 (已下载 {resume_pos / (1024*1024):.1f} MB)")
            
            # 设置请求头
            headers = {}
            if resume_pos > 0:
                headers['Range'] = f'bytes={resume_pos}-'
            
            req = urllib.request.Request(url, headers=headers)
            
            # 开始下载
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                if resume_pos > 0:
                    total_size += resume_pos
                
                mode = 'ab' if resume_pos > 0 else 'wb'
                with open(temp_file, mode) as f:
                    downloaded = resume_pos
                    chunk_size = 8192
                    last_update = time.time()
                    
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 更新进度（每秒一次）
                        now = time.time()
                        if progress_callback and (now - last_update > 1.0 or downloaded >= total_size):
                            percent = (downloaded / total_size * 100) if total_size > 0 else 0
                            mb_downloaded = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            progress_callback(f"下载中: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
                            last_update = now
            
            # 下载完成，重命名
            temp_file.rename(filepath)
            
            if progress_callback:
                progress_callback(f"下载完成: {filepath.name}")
            
            return True
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"下载失败: {e}")
            logger.error(f"下载失败: {e}")
            return False
    
    def _get_package_dependencies(self, package_name: str) -> List[str]:
        """获取包的依赖列表"""
        # 常见依赖映射
        deps_map = {
            "torch": ["filelock", "typing-extensions", "sympy", "networkx", "jinja2", "fsspec"],
            "kornia": [],
            "ortools": []
        }
        return deps_map.get(package_name, [])
    
    def clear_cache(self):
        """清理缓存"""
        for file in self.cache_dir.glob("*.whl"):
            try:
                file.unlink()
            except:
                pass
        
        for file in self.cache_dir.glob("*.tmp"):
            try:
                file.unlink()
            except:
                pass


def main():
    """测试"""
    logging.basicConfig(level=logging.INFO)
    
    manager = PackageManager()
    
    print("已安装的包:", manager.get_installed_packages())
    print("缺失的包:", manager.get_missing_packages())
    
    # 测试安装
    def progress(msg):
        print(f"  {msg}")
    
    success, log = manager.install_package("opencv-cpu", progress)
    print(f"安装结果: {'成功' if success else '失败'}")


if __name__ == "__main__":
    main()
