@echo off
setlocal
cd /d "%~dp0"

:: Check venv exists
if not exist "venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Please install Python 3.10+
        pause
        exit /b 1
    )
    echo [*] Installing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [+] Setup complete.
    echo.
)

:: Launch
chcp 65001 >nul 2>&1
title Roco Navigator
echo ============================================
echo   Roco Navigator
echo ============================================
echo.

set PYTHONPATH=%~dp0..
venv\Scripts\python.exe -m roco_navigator.main

if errorlevel 1 (
    echo.
    echo [ERROR] Exit code: %errorlevel%
    pause
)
