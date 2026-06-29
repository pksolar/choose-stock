@echo off
chcp 65001 >nul
title V-Stock Radar - No Docker Launcher
cd /d "%~dp0"

echo =========================================
echo   V-Stock Radar - No Docker YiJian QiDong
echo =========================================
echo.

:: ==========================================
:: 1. JianCha Python
:: ==========================================
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
    echo [XX] Wei JianCe Dao Python, Qing AnZhuang Python 3.10+
    echo      XiaZai: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do echo [OK] %%i

:: ==========================================
:: 2. JianCha Node.js
:: ==========================================
where node >nul 2>&1
if errorlevel 1 (
    echo [XX] Wei JianCe Dao Node.js, Qing AnZhuang Node.js 18+
    echo      XiaZai: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo [OK] Node.js %%i

echo.

:: ==========================================
:: 3. ZhunBei .env PeiZhi
:: ==========================================
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] Yi ChuangJian .env PeiZhi

    :: SheZhi USE_MOCK_DATA=false (QiYong ZhenShi PaChong)
    %PYTHON_CMD% -c "f=open('.env','r');c=f.read();f.close();c=c.replace('USE_MOCK_DATA=true','USE_MOCK_DATA=false');f=open('.env','w');f.write(c);f.close()"
    echo [OK] Yi KaiQi ZhenShi PaChong MoShi (USE_MOCK_DATA=false^)
) else (
    echo [OK] .env PeiZhi Yi CunZai
)

:: ==========================================
:: 4. AnZhuang Python YiLai + QiDong HouDuan
:: ==========================================
echo.
echo =========================================
echo [1/2] AnZhuang Bing QiDong HouDuan...
echo =========================================

cd /d "%~dp0backend"

echo [..] pip install -r requirements.txt
%PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
if errorlevel 1 (
    echo [..] QingHua Yuan ShiBai, ChangShi MoRen Yuan...
    %PYTHON_CMD% -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [XX] Python YiLai AnZhuang ShiBai, Qing JianCha WangLuo
        pause
        exit /b 1
    )
)
echo [OK] Python YiLai AnZhuang WanCheng

:: AnZhuang Playwright Chromium LiuLanQi (ShouCi YunXing XuYao)
echo [..] JianCha Playwright Chromium...
%PYTHON_CMD% -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('OK')" >nul 2>&1
if errorlevel 1 (
    echo [..] ShouCi YunXing, ZhengZai XiaZai Chromium (~150MB^)...
    %PYTHON_CMD% -m playwright install chromium
    if errorlevel 1 (
        echo [!!] Chromium XiaZai ShiBai, PaChong Jiang ShiYong MoNi ShuJu MoShi
        echo      ShouDong AnZhuang: playwright install chromium
    ) else (
        echo [OK] Chromium AnZhuang WanCheng
    )
) else (
    echo [OK] Chromium Yi ZhunBei JiuXu
)

:: QiDong HouDuan (WuXu Celery/Redis, HouDuan Hui ZiDong QieHuan Dao DuoXianCheng MoShi)
echo [OK] QiDong FastAPI HouDuan (DuanKou 8000^)...
start "VStock-Backend" /D "%~dp0backend" cmd /k "%PYTHON_CMD% main.py"

cd /d "%~dp0"

:: ==========================================
:: 5. AnZhuang QianDuan YiLai + QiDong QianDuan
:: ==========================================
echo.
echo =========================================
echo [2/2] AnZhuang Bing QiDong QianDuan...
echo =========================================

cd /d "%~dp0frontend"

echo [..] npm install
call npm install --registry=https://registry.npmmirror.com
if errorlevel 1 (
    echo [..] TaoBao Yuan ShiBai, ChangShi MoRen Yuan...
    call npm install
    if errorlevel 1 (
        echo [XX] QianDuan YiLai AnZhuang ShiBai
        pause
        exit /b 1
    )
)
echo [OK] npm YiLai AnZhuang WanCheng

echo [OK] QiDong QianDuan KaiFa FuWuQi (DuanKou 5173^)...
start "VStock-Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 0.0.0.0"

cd /d "%~dp0"

:: ==========================================
:: 6. DaKai LiuLanQi
:: ==========================================
echo.
echo [..] DengDai HouDuan QiDong...
timeout /t 5 /nobreak >nul

start http://localhost:5173

:: ==========================================
echo.
echo =========================================
echo   SuoYou FuWu Yi QiDong!
echo.
echo   QianDuan:     http://localhost:5173
echo   HouDuan API:  http://localhost:8000
echo   API WenDang:  http://localhost:8000/docs
echo.
echo   MoShi: MoNi ShuJu (USE_MOCK_DATA=true^)
echo   BeiZhu: WuXu Docker/Redis/Celery
echo.
echo   GuanBi GeGe ChuangKou JiKe TingZhi SuoYou FuWu
echo =========================================
echo.

pause
