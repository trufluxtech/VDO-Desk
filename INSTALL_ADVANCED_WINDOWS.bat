@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title VDODesk advanced tracking setup
chcp 65001 >nul 2>nul

echo Installing optional OpenCV tracking and segmentation support...
set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
  goto :install
)

where py.exe >nul 2>nul
if not errorlevel 1 for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto :create_venv

where python.exe >nul 2>nul
if errorlevel 1 goto :missing_python
for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE goto :missing_python

:create_venv
"%PYTHON_EXE%" -m venv .venv
if errorlevel 1 goto :failed
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

:install
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%PYTHON_EXE%" -m pip install -r requirements-advanced.txt
if errorlevel 1 goto :failed
echo.
echo Advanced OpenCV support is installed. START_WINDOWS.bat will use it automatically.
pause
exit /b 0

:missing_python
echo Python was not found. Run SETUP_WINDOWS.bat first.
pause
exit /b 1

:failed
echo.
echo OpenCV installation failed. The main editor still works without it.
pause
exit /b 1
