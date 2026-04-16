@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: ================================================
::            洛克王国导航助手 v1.0.0
:: ================================================

:: 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请安装 Python 3.10+ 并添加到 PATH
    echo        下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 Python 版本
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [信息] Python 版本: %PYVER%

:: 创建虚拟环境 (首次运行)
if not exist "venv\Scripts\python.exe" (
    echo.
    echo [*] 首次运行，正在配置环境...
    echo.
    echo [1/2] 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [2/2] 安装依赖 (可能需要几分钟)...
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

:: 检查 OpenCV (DLL加载失败时自动切换CPU版本)
venv\Scripts\python.exe -c "import cv2" >nul 2>&1
if errorlevel 1 (
    echo [*] OpenCV 加载失败，正在切换到 CPU 版本...
    venv\Scripts\pip.exe uninstall opencv-contrib-python -y >nul 2>&1
    venv\Scripts\pip.exe install opencv-python>=4.8.0
    if errorlevel 1 (
        echo [错误] OpenCV 安装失败
        pause
        exit /b 1
    )
    echo [OK] OpenCV CPU 版本已安装
)

:: 启动
title 洛克王国导航助手
echo ================================================
echo            洛克王国导航助手 v1.0.0
echo ================================================
echo.

set PYTHONPATH=%~dp0..
venv\Scripts\python.exe -m roco_navigator.main

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出 (代码: !errorlevel!)
    pause
)
