@echo off
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

echo ========================================================
echo   Pokemon Stock Shorts Automation Pipeline
echo ========================================================
echo.
:: Run with market argument (e.g., run_pipeline.bat KR)
set MARKET=%~1
if "%MARKET%"=="" set MARKET=US

echo [1/1] Running Unified Pipeline for Market: %MARKET%...
echo.

"C:\Users\HanEx\.antigravity\.venv\Scripts\python.exe" shorts_pipeline.py --market %MARKET%

echo.
echo ========================================================
echo   Task Completed Successfully.
echo ========================================================
pause
