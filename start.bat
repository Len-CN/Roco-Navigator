@echo off
cd /d "%~dp0"
title Roco Navigator
call :main
echo.
pause
exit /b

:main
echo ================================================
echo             Roco Navigator v3.0.1
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    echo         Install Python 3.10 or 3.11 and add it to PATH
    echo         https://www.python.org/downloads/
    goto :eof
)

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PY_VERSION=%%V
echo [*] System Python: %PY_VERSION%
echo     Recommended for this project: Python 3.10 or 3.11
echo.

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

venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Existing venv is broken or points to a removed Python install.
    echo         This can happen after uninstalling the Python version used to create it.
    echo.
    echo         Recommended fix:
    echo           1. Install Python 3.10 or 3.11
    echo           2. Rename or delete the old venv folder
    echo           3. Run start.bat again
    echo.
    echo         Current folder: %cd%\venv
    goto :eof
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
