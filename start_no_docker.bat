@echo off
chcp 65001 >nul 2>&1
title V-Stock Radar Launcher
cd /d "%~dp0"

echo =========================================
echo   V-Stock Radar - Quick Start
echo =========================================
echo.

:: Check Python
set PYTHON_CMD=
where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
) else (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=python3
    )
)

if "%PYTHON_CMD%"=="" (
    echo [XX] Python not found. Please install Python 3.10+
    echo      https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do echo [OK] %%i

:: Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [XX] Node.js not found. Please install Node.js 18+
    echo      https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo [OK] Node.js %%i
echo.

:: .env config
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] Created .env from .env.example
) else (
    echo [OK] .env config exists
)

:: Backend
echo.
echo =========================================
echo [1/2] Installing Python dependencies...
echo =========================================
cd /d "%~dp0backend"
echo [..] pip install -r requirements.txt
%PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [..] Tsinghua mirror failed, trying default...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [XX] Python dependency install failed
        pause
        exit /b 1
    )
)
echo [OK] Python dependencies installed

:: Start Backend
cd /d "%~dp0"
echo [OK] Starting Backend on port 8000...
start "VStock-Backend" /D "%~dp0backend" cmd /k "%PYTHON_CMD% main.py"

:: Frontend
echo.
echo =========================================
echo [2/2] Installing and starting Frontend...
echo =========================================
cd /d "%~dp0frontend"
echo [..] npm install
call npm install --registry=https://registry.npmmirror.com
if errorlevel 1 (
    echo [..] Mirror failed, trying default registry...
    call npm install
    if errorlevel 1 (
        echo [XX] Frontend dependency install failed
        pause
        exit /b 1
    )
)
echo [OK] npm dependencies installed
echo [OK] Starting Frontend on port 5173...
start "VStock-Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 0.0.0.0"
cd /d "%~dp0"

:: Open browser
echo.
echo [..] Waiting for services to start...
timeout /t 6 /nobreak >nul
start http://localhost:5173

echo.
echo =========================================
echo   All services started!
echo.
echo   Frontend:     http://localhost:5173
echo   Backend API:  http://localhost:8000
echo.
echo   Note: First run will download Playwright
echo   Chromium automatically if needed.
echo.
echo   Close CMD windows to stop services
echo =========================================
echo.
pause
