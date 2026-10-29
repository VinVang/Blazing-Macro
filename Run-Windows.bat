@echo off
setlocal
cd /d "%~dp0"
title Blazing Revival - Ninja Road

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] First-time setup: creating a private Python environment...
  py -3 -m venv .venv 2>nul
  if errorlevel 1 python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
    echo Then run this file again.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import cv2, mss, pyautogui, PIL, numpy, requests, discord" >nul 2>&1
if errorlevel 1 (
  echo [SETUP] Installing libraries from PyPI, first launch only...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Library install failed. Verify network connection and retry.
    pause
    exit /b 1
  )
)

echo [START] Ninja Road macro GUI...
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
  echo.
  echo The macro exited with an error. See the text above.
  pause
)
endlocal
