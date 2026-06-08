@echo off
cd /d "%~dp0\.."
echo Installing dependencies...
py -3 -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1
if not exist "data\grocery_sales_realistic.csv" (
  echo Generating grocery sales data...
  py -3 scripts\generate_grocery_sales.py
)
echo Checking MySQL setup...
py -3 backend\setup_database.py
if errorlevel 1 exit /b 1
echo.
echo Starting server — use the URL printed below
py -3 backend\serve_dashboard.py
