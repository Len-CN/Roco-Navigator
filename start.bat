@echo off
chcp 65001 >nul 2>&1
title 洛克导航 - Roco Navigator

echo ============================================
echo   洛克导航 (Roco Navigator) 启动中...
echo ============================================
echo.

:: 进入项目目录
cd /d "%~dp0"

:: 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [!] 虚拟环境不存在，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确保已安装 Python 3.10+
        pause
        exit /b 1
    )
    echo [+] 虚拟环境创建完成
    echo [*] 正在安装依赖...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo [+] 依赖安装完成
    echo.
)

:: 启动程序
echo [*] 正在启动洛克导航...
echo.
venv\Scripts\python.exe -m roco_navigator.main

:: 如果异常退出，暂停显示错误
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出 (错误代码: %errorlevel%)
    pause
)
