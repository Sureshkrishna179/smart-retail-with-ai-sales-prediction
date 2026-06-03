@echo off
cd /d "%~dp0"
echo Checking MySQL setup...
py -3 backend\setup_database.py
if errorlevel 1 exit /b 1
echo.
echo Starting server...
py -3 backend\serve_dashboard.py
