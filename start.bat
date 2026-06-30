@echo off
title V-Stock Radar Launcher
cd /d "%~dp0"

echo =========================================
echo   V-Stock Radar - DaV YuQing JuHeQi
echo   YiJian QiDong JiaoBen (Windows)
echo =========================================
echo.

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    where python3 >nul 2>&1
    if errorlevel 1 (
        echo [XX] Python not found. Please install Python 3.10+
        echo      Download: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [OK] %%i

:: Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [XX] Node.js not found. Please install Node.js 18+
    echo      Download: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo [OK] Node.js %%i

echo.
echo =========================================
echo [1/2] Installing and starting Backend...
echo =========================================

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] Created .env from .env.example
)

:: Enter backend directory
cd /d "%~dp0backend"

:: Install Python dependencies
echo [..] pip install -r requirements.txt
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [!!] pip install failed, trying default mirror...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [XX] Python dependency install failed
        pause
        exit /b 1
    )
)

:: Start Backend
cd /d "%~dp0"
echo [OK] Starting FastAPI Backend (port 8000)...
start "VStock-Backend" cmd /k "cd /d \"%~dp0backend\" && python main.py"

echo.
echo =========================================
echo [2/2] Installing and starting Frontend...
echo =========================================

cd /d "%~dp0frontend"

echo [..] npm install
call npm install --registry=https://registry.npmmirror.com
if errorlevel 1 (
    echo [!!] npm install failed, trying default mirror...
    call npm install
    if errorlevel 1 (
        echo [XX] Frontend dependency install failed
        pause
        exit /b 1
    )
)

start "VStock-Frontend" cmd /k "cd /d \"%~dp0frontend\" && npm run dev -- --host 0.0.0.0"

cd /d "%~dp0"

echo.
echo =========================================
echo   All services started!
echo   - Backend API:  http://localhost:8000
echo   - API Docs:     http://localhost:8000/docs
echo   - Frontend:     http://localhost:5173
echo =========================================
echo.
echo   Close all CMD windows to stop services
echo.

pause
