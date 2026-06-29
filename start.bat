@echo off
title V-Stock Radar Launcher
cd /d "%~dp0"

echo =========================================
echo   V-Stock Radar - DaV YuQing JuHeQi
echo   YiJian QiDong JiaoBen (Windows)
echo =========================================
echo.

:: ==========================================
:: FangShi Yi: Docker QiDong
:: ==========================================
where docker >nul 2>&1
if not errorlevel 1 (
    echo [OK] JianCe Dao Docker

    if not exist ".env" (
        copy ".env.example" ".env" >nul
        echo [OK] Yi ChuangJian .env PeiZhi
    )

    echo [..] QiDong Docker RongQi...
    docker compose up -d --build
    if not errorlevel 1 (
        echo.
        echo =========================================
        echo   SuoYou FuWu Yi QiDong!
        echo   QianDuan:  http://localhost:5173
        echo   HouDuan:  http://localhost:8000
        echo   API WenDang: http://localhost:8000/docs
        echo =========================================
        echo.
        pause
        exit /b 0
    ) else (
        echo [XX] Docker QiDong ShiBai, QieHuan Dao BenDi MoShi...
        echo.
    )
)

:: ==========================================
:: FangShi Er: BenDi KaiFa MoShi
:: ==========================================
echo =========================================
echo   BenDi KaiFa MoShi
echo =========================================
echo.

:: JianCha Python
where python >nul 2>&1
if errorlevel 1 (
    where python3 >nul 2>&1
    if errorlevel 1 (
        echo [XX] Wei JianCe Dao Python, Qing AnZhuang Python 3.10+
        echo      XiaZai: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [OK] %%i

:: JianCha Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [XX] Wei JianCe Dao Node.js, Qing AnZhuang Node.js 18+
    echo      XiaZai: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo [OK] Node.js %%i

:: JianCha Redis
where redis-cli >nul 2>&1
if errorlevel 1 (
    echo [!!] Wei JianCe Dao Redis
    echo      Qing QueBao Redis FuWu Zai BenDi 6379 DuanKou YunXing
    echo      Ruo Wu Redis, TuiJian ShiYong Docker: docker compose up -d
    echo      HuoZhe XiaZai Redis for Windows
    echo.
    echo      An RenYi Jian JiXu (Hui Yin Redis QueShi Er ShiBai)...
    pause
)

echo.
echo =========================================
echo [1/3] AnZhuang Python YiLai Bing QiDong HouDuan...
echo =========================================

:: JinRu HouDuan MuLu
cd /d "%~dp0backend"

:: AnZhuang Python YiLai
echo [..] pip install -r requirements.txt
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [!!] Python YiLai AnZhuang ShiBai, ChangShi ShiYong MoRen Yuan...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [XX] Python YiLai AnZhuang ShiBai, Qing JianCha WangLuo
        pause
        exit /b 1
    )
)

:: QiDong HouDuan (Xin ChuangKou)
echo [OK] QiDong FastAPI HouDuan (DuanKou 8000)...
start "VStock-Backend" /D "%~dp0backend" cmd /k "python main.py"

:: QiDong Celery Worker (Xin ChuangKou)
echo [OK] QiDong Celery Worker...
start "VStock-Celery" /D "%~dp0backend" cmd /k "celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo"

echo.
echo =========================================
echo [2/3] AnZhuang QianDuan YiLai...
echo =========================================

cd /d "%~dp0frontend"

echo [..] npm install
call npm install --registry=https://registry.npmmirror.com
if errorlevel 1 (
    echo [!!] npm AnZhuang ShiBai, ChangShi ShiYong MoRen Yuan...
    call npm install
    if errorlevel 1 (
        echo [XX] QianDuan YiLai AnZhuang ShiBai
        pause
        exit /b 1
    )
)

echo.
echo =========================================
echo [3/3] QiDong QianDuan KaiFa FuWuQi...
echo =========================================

start "VStock-Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 0.0.0.0"

cd /d "%~dp0"

echo.
echo =========================================
echo   SuoYou FuWu Yi QiDong!
echo   - HouDuan API:  http://localhost:8000
echo   - API WenDang:  http://localhost:8000/docs
echo   - QianDuan:     http://localhost:5173
echo =========================================
echo.
echo   GuanBi GeGe ChuangKou JiKe TingZhi FuWu
echo   (MeiGe FuWu Zai DuLi ChuangKou Zhong YunXing)
echo.
echo   RuGuo Redis WeiQiDong, Qing Zai LingYiGe ChuangKou YunXing:
echo     redis-server
echo.

pause
