@echo off
chcp 65001 >nul
title BanContentAuto Studio Dashboard - Khoi Dong He Thong

echo =====================================================================
echo           BANCONTENT AUTO STUDIO - KHOI DONG HE THONG TU DONG
echo =====================================================================
echo.

:: 1. Chuyen toi thu muc hien tai chua script
cd /d "%~dp0"

:: 2. Thiet lap bien moi truong PYTHONPATH tro vao src
set PYTHONPATH=%cd%\src;%PYTHONPATH%

:: 3. Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.11+ va tich vao "Add Python to PATH".
    echo Nhan phim bat ky de thoat...
    pause >nul
    exit /b 1
)

:: 4. Kiem tra thu muc can thiet
if not exist "bin" mkdir bin
if not exist "downloads" mkdir downloads
if not exist "renders" mkdir renders
if not exist "cache" mkdir cache

echo [*] Kiem tra nhanh cong cu ho tro:
python -c "import sys, os; sys.path.insert(0, os.path.abspath('src')); from autovideo.core.binary_manager import BinaryManager; bm = BinaryManager(); info = bm.check_all(); print('  - ffmpeg:  ', info['ffmpeg'].version if info.get('ffmpeg') and info['ffmpeg'].is_available else '[CANH BAO]'); print('  - ffprobe: ', info['ffprobe'].version if info.get('ffprobe') and info['ffprobe'].is_available else '[CANH BAO]'); print('  - yt-dlp:  ', info['yt-dlp'].version if info.get('yt-dlp') and info['yt-dlp'].is_available else '[OK - Python package]');"

echo.
echo =====================================================================
echo [*] Dang khoi dong Web Dashboard...
echo [*] Neu cong 8000 bi chiem, he thong se tu dong chuyen sang cong trong (8001, 8002...)
echo [*] Trinh duyet web se tu dong mo trong giay lat...
echo [*] Nhan Ctrl + C de dung may chu khi can.
echo =====================================================================
echo.

:: 5. Chay ung dung qua app.py
python app.py --open-browser

pause
