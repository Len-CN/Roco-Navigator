@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Check venv exists
if not exist "venv\Scripts\python.exe" (
    echo [*] 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确认已安装 Python 3.10+
        pause
        exit /b 1
    )
    echo [*] 正在安装依赖...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 安装依赖失败
        pause
        exit /b 1
    )
    echo [OK] 环境配置完成
    echo.
)

:: Launch
title 洛克王国导航助手
echo ============================================
echo   洛克王国导航助手
echo ============================================
echo.

set PYTHONPATH=%~dp0..
venv\Scripts\python.exe -m roco_navigator.main

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出 (代码: !errorlevel!)
    pause
)
