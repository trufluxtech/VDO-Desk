@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title VDODesk local editor
chcp 65001 >nul 2>nul

echo.
echo ============================================================
echo   VDODesk - Windows 10/11 launcher
echo ============================================================
echo.

where ffmpeg.exe >nul 2>nul
if errorlevel 1 goto :missing_ffmpeg
where ffprobe.exe >nul 2>nul
if errorlevel 1 goto :missing_ffmpeg

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if defined PYTHON_EXE goto :check_python

where py.exe >nul 2>nul
if errorlevel 1 goto :try_python
for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto :check_python

:try_python
where python.exe >nul 2>nul
if errorlevel 1 goto :missing_python
for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE goto :missing_python

:check_python
"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python

echo Python: "%PYTHON_EXE%"
for /f "delims=" %%F in ('where ffmpeg.exe') do if not defined FFMPEG_EXE set "FFMPEG_EXE=%%F"
echo FFmpeg: "%FFMPEG_EXE%"
echo.
echo Starting VDODesk. Keep this window open while editing.
echo Press Ctrl+C here when you want to stop the editor.
echo.
"%PYTHON_EXE%" app\server.py %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo VDODesk stopped with error code %EXIT_CODE%.
  echo Review the message above, then press any key to close.
  pause >nul
)
exit /b %EXIT_CODE%

:missing_ffmpeg
echo FFmpeg and FFprobe were not found on PATH.
echo Run SETUP_WINDOWS.bat, then close and reopen this folder before starting VDODesk.
echo.
pause
exit /b 1

:missing_python
echo Python 3.10 or newer was not found.
echo Run SETUP_WINDOWS.bat, then close and reopen this folder before starting VDODesk.
echo.
pause
exit /b 1

:old_python
echo VDODesk requires Python 3.10 or newer.
echo Run SETUP_WINDOWS.bat to install a supported Python version.
echo.
pause
exit /b 1
