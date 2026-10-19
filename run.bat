@echo off
title Multi-Token-Voice Safe Launcher
cls

echo ====================================================
echo         MULTI-TOKEN VOICE LAUNCHER (Windows)
echo ====================================================

REM 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python chua duoc cai dat! Vui long cai Python va tich chon "Add to PATH".
    pause
    exit /b
)

REM 2. Create/Check Venv
if exist ".venv" goto :activate_venv

echo [INFO] Dang tao moi truong ao (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] Khong the tao venv.
    pause
    exit /b
)

echo [INFO] Dang cai dat thu vien (lan dau)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
goto :run_bot

:activate_venv
echo [INFO] Phat hien moi truong ao san co.
call .venv\Scripts\activate.bat

:run_bot
REM 3. Run Dashboard
echo [INFO] Dang khoi dong Bot...
echo ----------------------------------------------------
python dashboard.py
echo ----------------------------------------------------

echo [INFO] Bot da dung.
pause
