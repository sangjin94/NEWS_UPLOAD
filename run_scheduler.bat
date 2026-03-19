@echo off
echo ===================================================
echo   Stock News Shorts Scheduler Launcher
echo ===================================================
echo.
echo [1/2] Checking dependencies...
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv is missing! Please install dependencies first.
    pause
    exit /b
)

".venv\Scripts\python.exe" -m pip install -q schedule

echo [2/2] Launching GUI...
start "" ".venv\Scripts\python.exe" scheduler_gui.py
echo.
echo Scheduler launched successfully. You can close this window.
timeout /t 3
exit
