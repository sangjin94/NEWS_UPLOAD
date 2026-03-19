@echo off
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

echo ========================================================
echo   Pokemon Stock Shorts Automation Pipeline
echo ========================================================
echo.
echo [1/1] Running Unified Pipeline...
echo.

:: Run the unified python script with absolute python path
"C:\Users\HanEx\.antigravity\.venv\Scripts\python.exe" shorts_pipeline.py

echo.
echo ========================================================
echo   Task Completed Successfully.
echo ========================================================
pause
