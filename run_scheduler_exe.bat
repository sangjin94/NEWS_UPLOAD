@echo off
cd /d "%~dp0"
if exist "dist\SchedulerGUI.exe" (
    echo [INFO] Running Scheduler GUI Executable...
    dist\SchedulerGUI.exe
) else (
    echo [ERROR] SchedulerGUI.exe not found in dist folder.
    pause
)
