@echo off
setlocal

REM Try to find working python
set "VENV_PY=c:\MY Projects\Project AI Sales\.venv\Scripts\python.exe"

echo Checking Python environments...
echo.

echo === venv python ===
"%VENV_PY%" --version 2>&1
echo.

echo === venv installed packages ===
"%VENV_PY%" -c "import pkg_resources; pkgs = sorted(p.key for p in pkg_resources.working_set); [print(p) for p in pkgs]" 2>&1
echo.

echo === Can import lightgbm? ===
"%VENV_PY%" -c "import lightgbm; print('lightgbm OK', lightgbm.__version__)" 2>&1

echo === Can import matplotlib? ===
"%VENV_PY%" -c "import matplotlib; print('matplotlib OK', matplotlib.__version__)" 2>&1

echo === Can import scipy? ===
"%VENV_PY%" -c "import scipy; print('scipy OK', scipy.__version__)" 2>&1

echo === Can import sklearn? ===
"%VENV_PY%" -c "import sklearn; print('sklearn OK', sklearn.__version__)" 2>&1
