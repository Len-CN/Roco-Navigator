@echo off
cd /d "%~dp0"
title Roco Navigator
call :main
echo.
pause
exit /b

:main
echo ================================================
echo             Roco Navigator v1.0.0
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    echo         Install Python 3.10+ and add to PATH
    echo         https://www.python.org/downloads/
    goto :eof
)

if not exist "venv\Scripts\python.exe" (
    echo [1/2] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed
        goto :eof
    )
    echo [2/2] Installing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed
        goto :eof
    )
    echo.
    echo [OK] Setup complete
    echo.
)

venv\Scripts\python.exe -c "import PyQt5; import numpy; import mss; import cv2" >nul 2>&1
if errorlevel 1 (
    echo [*] Fixing missing dependencies...
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed
        goto :eof
    )
)

echo [*] Starting...
set PYTHONPATH=%~dp0..
venv\Scripts\python.exe main.py
goto :eof
