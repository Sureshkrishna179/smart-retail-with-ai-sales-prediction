@echo off
setlocal
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
set "SCRIPT=%~dp0forecast_lgbm.py"
set PYTHONIOENCODING=utf-8

echo ============================================================
echo  AI Sales Forecasting Pipeline (Detrended HGBR)
echo ============================================================
echo.

REM Quick sanity check - verify required packages
echo Checking required packages...
"%PYTHON%" -c "import scipy, sklearn, numpy, pandas; print('  scipy', scipy.__version__, '  sklearn', sklearn.__version__, '  numpy', numpy.__version__, '  pandas', pandas.__version__)"
if errorlevel 1 (
    echo ERROR: Missing required packages. Please install scipy and scikit-learn.
    exit /b 1
)

REM Optional: check matplotlib
"%PYTHON%" -c "import matplotlib; print('  matplotlib', matplotlib.__version__)" 2>nul || echo   matplotlib not available - charts will be saved as CSV

echo.
echo Running pipeline...
echo ============================================================
"%PYTHON%" "%SCRIPT%"
echo ============================================================
echo.
echo Output files in: %~dp0..\files\output\
