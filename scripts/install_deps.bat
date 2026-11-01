@echo off
setlocal
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"

echo Installing packages into .venv ...
"%PYTHON%" -m pip install lightgbm matplotlib scipy scikit-learn

echo.
echo Verifying imports ...
"%PYTHON%" -c "import lightgbm; print('lightgbm', lightgbm.__version__)"
"%PYTHON%" -c "import matplotlib; print('matplotlib', matplotlib.__version__)"
"%PYTHON%" -c "import scipy; print('scipy', scipy.__version__)"
"%PYTHON%" -c "import sklearn; print('sklearn', sklearn.__version__)"
echo.
echo All done.
