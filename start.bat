@echo off
setlocal
cd /d "%~dp0"

:: Check venv exists
if not exist "venv\Scripts\python.exe" (
    echo [*] 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。请安装 Python 3.10+
        pause
        exit /b 1
    )
    echo [*] 正在安装基础依赖...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 安装依赖失败。
        pause
        exit /b 1
    )
    echo [+] 环境配置完成。
    echo.
)

:: Launch with dependency checker
chcp 65001 >nul 2>&1
title 洛克导航
echo ============================================
echo   洛克导航
echo ============================================
echo.

set PYTHONPATH=%~dp0..
venv\Scripts\python.exe -m roco_navigator.main

if errorlevel 1 (
    echo.
    echo [错误] 退出代码: %errorlevel%
    pause
)
