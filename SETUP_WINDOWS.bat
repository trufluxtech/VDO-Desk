@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title VDODesk Windows setup
chcp 65001 >nul 2>nul

echo.
echo ============================================================
echo   VDODesk prerequisite setup for Windows 10/11
echo ============================================================
echo.
echo This optional helper uses Windows Package Manager to install:
echo   - Python 3.12 (Python.Python.3.12)
echo   - FFmpeg full build (Gyan.FFmpeg)
echo.
choice /C YN /N /M "Continue with installation? [Y/N] "
if errorlevel 2 exit /b 0

where winget.exe >nul 2>nul
if errorlevel 1 goto :missing_winget

echo.
echo Installing or confirming Python 3.12...
winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :install_failed

echo.
echo Installing or confirming FFmpeg...
winget install --id Gyan.FFmpeg --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :install_failed

echo.
echo Setup completed.
echo IMPORTANT: Close this window so Windows refreshes PATH, then double-click START_WINDOWS.bat.
pause
exit /b 0

:missing_winget
echo.
echo Windows Package Manager was not found. Update or install "App Installer"
echo from Microsoft Store, or install the prerequisites manually:
echo   Python: https://www.python.org/downloads/windows/
echo   FFmpeg: https://ffmpeg.org/download.html
echo.
echo During Python installation, enable "Add python.exe to PATH".
pause
exit /b 1

:install_failed
echo.
echo A prerequisite installation did not finish successfully.
echo Review the winget message above. You can also install manually using
echo the official links shown in docs\WINDOWS.md.
pause
exit /b 1
