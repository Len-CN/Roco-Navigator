@echo off
chcp 65001 >/dev/null 2>&1
cd /d "%~dp0"

echo ============================================
echo   OpenCV CPU 版本安装
echo ============================================
echo.

if not exist "venv\Scripts\pip.exe" (
    echo [错误] 未找到虚拟环境，请先运行 start.bat
    pause
    exit /b 1
)

echo [*] 正在卸载 CUDA 版本...
venv\Scripts\pip.exe uninstall opencv-contrib-python -y 2>/dev/null
venv\Scripts\pip.exe uninstall opencv-python -y 2>/dev/null

echo [*] 正在安装 CPU 版本...
venv\Scripts\pip.exe install opencv-python>=4.8.0

if errorlevel 1 (
    echo.
    echo [错误] 安装失败
    pause
    exit /b 1
)

echo.
echo [OK] OpenCV CPU 版本安装成功，请重新启动程序
pause
