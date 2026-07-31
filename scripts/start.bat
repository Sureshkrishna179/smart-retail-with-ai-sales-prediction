@echo off
cd /d "%~dp0\.."

set PY_EXEC=py -3
if exist ".venv\Scripts\python.exe" (
    set PY_EXEC=.venv\Scripts\python.exe
)

echo Installing dependencies...
%PY_EXEC% -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

if not exist "data\grocery_sales_realistic.csv" (
    echo Generating grocery sales data...
    %PY_EXEC% scripts\generate_grocery_sales.py
)

echo Checking MySQL setup...
set PYTHONPATH=src
%PY_EXEC% src\smartretail\db\migrations\setup_database.py
if errorlevel 1 exit /b 1

echo.
echo Starting server...
echo Open http://localhost:8765/ in your browser.
echo.
%PY_EXEC% -m smartretail.server
