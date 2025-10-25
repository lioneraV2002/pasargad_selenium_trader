@echo off
echo --- Automated Build Environment Setup ---
SETLOCAL

REM Check if Python is installed
python --version >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in your PATH.
    echo Please install Python 3.8+ and add it to your PATH.
    pause
    GOTO :EOF
)
echo Python found.

REM --- 1. Create Virtual Environment ---
IF NOT EXIST "venv" (
    echo Creating virtual environment in 'venv' folder...
    python -m venv venv
) ELSE (
    echo Virtual environment 'venv' already exists.
)

REM --- 2. Install All Requirements ---
echo Installing all project requirements (pyinstaller, pandas, easyocr, selenium)...
REM We call the python.exe from INSIDE the venv to ensure packages
REM are installed in the venv, not globally.
.\venv\Scripts\python.exe -m pip install -r requirements.txt

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install requirements.
    pause
    GOTO :EOF
)
echo Requirements installed successfully.

REM --- 3. Build the Executable ---
echo Building 'algotrader.exe'...
REM We call the pyinstaller.exe from INSIDE the venv.
.\venv\Scripts\pyinstaller.exe --onefile ^
    --name "algotrader" ^
    --collect-all "easyocr" ^
    --collect-all "pandas" ^
    stock_trader.py

IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller build failed.
    pause
    GOTO :EOF
)

echo --- Build Complete! ---
echo Your executable is in the 'dist' folder.
pause

ENDLOCAL
GOTO :EOF