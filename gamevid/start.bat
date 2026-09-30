@echo off
setlocal
cd /d "%~dp0"

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg was not found on PATH.
  echo Install it with:  winget install Gyan.FFmpeg
  echo then close and reopen this window.
  pause
  exit /b 1
)

if not exist .venv (
  echo First run: creating Python environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.10+ is required: https://www.python.org/downloads/
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install -q --disable-pip-version-check -r requirements.txt
if not exist .env copy .env.example .env >nul

start "" http://localhost:8000
python -m app
pause
