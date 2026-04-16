@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title 洛克王国导航助手
call :main
echo.
echo 按任意键退出...
pause >nul
exit /b

:main
echo ================================================
echo            洛克王国导航助手 v1.0.0
echo ================================================
echo.
echo 工作目录: %cd%
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python
    echo        请安装 Python 3.10+ 并勾选 Add to PATH
    echo        https://www.python.org/downloads/
    goto :eof
)

:: 首次运行: 创建环境 + 安装依赖
if not exist "venv\Scripts\python.exe" (
    echo [1/2] 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        goto :eof
    )
    echo [2/2] 安装依赖 (首次需要几分钟)...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        goto :eof
    )
    echo.
    echo [OK] 环境配置完成
    echo.
)

:: 检查 OpenCV
venv\Scripts\python.exe -c "import cv2" >nul 2>&1
if errorlevel 1 (
    echo [*] 修复 OpenCV...
    venv\Scripts\pip.exe uninstall opencv-contrib-python -y >nul 2>&1
    venv\Scripts\pip.exe install opencv-python>=4.8.0
)

:: 启动
echo [*] 启动中...
set PYTHONPATH=%~dp0..
venv\Scripts\python.exe main.py
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
)
goto :eof
