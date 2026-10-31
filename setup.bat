@echo off
chcp 65001 >nul
title BanContentAuto Studio - Cai Dat Moi Truong (Setup)

echo =====================================================================
echo        BANCONTENT AUTO STUDIO - CAI DAT TAT CA CAC GOI PHU THUOC
echo =====================================================================
echo.

:: 1. Chuyen toi thu muc hien tai chua file bat
cd /d "%~dp0"

:: 2. Thiet lap PYTHONPATH tro vao src
set PYTHONPATH=%cd%\src;%PYTHONPATH%

:: 3. Kiem tra su ton tai cua Python
echo [*] Buoc 1/4: Kiem tra phien ban Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren he thong!
    echo Vui long cai dat Python 3.11 hoac 3.12 tu trang chu https://www.python.org/
    echo LUU Y: Nho tich chon vao muc "Add Python to PATH" khi cai dat.
    echo.
    echo Nhan phim bat ky de thoat...
    pause >nul
    exit /b 1
)
python --version

:: 4. Nang cap pip va cai dat requirements.txt
echo.
echo [*] Buoc 2/4: Dang cai dat cac thu vien can thiet tu requirements.txt...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [CANH BAO] Co loi xay ra trong qua trinh cai dat thu vien Python.
) else (
    echo [OK] Cai dat thu vien Python hoan tat!
)

:: 5. Tao cac thu muc lam viec
if not exist "bin" mkdir bin
if not exist "downloads" mkdir downloads
if not exist "renders" mkdir renders
if not exist "cache" mkdir cache
if not exist "logs" mkdir logs
if not exist "config" mkdir config

:: 6. Cai dat / tai tu dong cac cong cu vao bin/
echo.
echo [*] Buoc 3/4: Thiet lap va tai tu dong cac cong cu nhan dang vao bin/ (ffmpeg, ffprobe, yt-dlp, BBDown)...
python scripts/download_binaries.py

:: 7. Chay script kiem tra toan dien he thong
echo.
echo [*] Buoc 4/4: Kiem tra toan dien moi truong va cac cong cu nhan dang:
echo.
python scripts/check_env.py

echo.
echo =====================================================================
echo [HOAN TAT] Ban co the chay file 'start.bat' de mo Dashboard ngay!
echo =====================================================================
echo.
pause
