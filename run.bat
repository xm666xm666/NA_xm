@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title NA Auto Configuration Tool

echo ========================================
echo   NA Auto Configuration Tool
echo ========================================
echo.

set "PYCMD="
where python >nul 2>nul && set "PYCMD=python"
if not defined PYCMD where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
    echo [ERROR] Python not found. Install Python 3.8+ and add to PATH.
    echo.
    pause
    exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [INFO] Creating virtual environment...
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
)

echo [INFO] Installing dependencies...
"%VENV_PY%" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo.
    pause
    exit /b 1
)

echo [INFO] Starting server...
echo [INFO] Open: http://127.0.0.1:8765/
echo [INFO] Press Ctrl+C to stop
echo.

"%VENV_PY%" app.py %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] Server failed with exit code %EXITCODE%
    echo.
    pause
)
exit /b %EXITCODE%
