@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

title 洛克王国导航助手

echo ================================================
echo            洛克王国导航助手 v1.0.0
echo ================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请安装 Python 3.10+ 并添加到 PATH
    echo        下载: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: 首次运行: 创建环境 + 安装依赖
if not exist "venv\Scripts\python.exe" (
    echo [1/2] 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [2/2] 安装依赖 (首次需要几分钟)...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 安装依赖失败
        pause
        exit /b 1
    )
    echo.
    echo [OK] 环境配置完成
    echo.
)

:: 检查 OpenCV
venv\Scripts\python.exe -c "import cv2" >nul 2>&1
if errorlevel 1 (
    echo [*] OpenCV 异常，正在修复...
    venv\Scripts\pip.exe uninstall opencv-contrib-python -y >nul 2>&1
    venv\Scripts\pip.exe install opencv-python>=4.8.0
)

:: 启动程序
echo [*] 启动中...
echo.
set PYTHONPATH=%~dp0..
venv\Scripts\python.exe -m roco_navigator.main

:: 无论正常退出还是异常，都暂停让用户看到输出
echo.
if errorlevel 1 (
    echo [错误] 程序异常退出 (代码: !errorlevel!)
) else (
    echo [信息] 程序已退出
)
pause
