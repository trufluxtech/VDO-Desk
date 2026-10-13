@echo off
cd /d "%~dp0"
where ffmpeg >nul 2>nul || (echo Install FFmpeg and add it to PATH & pause & exit /b 1)
python app\server.py
pause
