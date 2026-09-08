@echo off
setlocal EnableExtensions

REM EVAVO Local Image Generator - Windows launcher
REM The Python controller is the single source of truth for process lifecycle,
REM health validation, state files, logs and exit codes.

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python was not found. Install Python 3.10+ or create .venv.
        exit /b 2
    )
    set "PYTHON=python"
)

if not exist "%ROOT%evavo.py" (
    echo ERROR: Missing %ROOT%evavo.py
    echo This checkout is stale. Run: git pull --ff-only origin main
    exit /b 2
)

pushd "%ROOT%" >nul

echo.
echo ============================================================
echo EVAVO Local Image Generator - Service Startup
echo ============================================================
echo Python: %PYTHON%
echo.

"%PYTHON%" "%ROOT%evavo.py" doctor
if errorlevel 2 (
    echo.
    echo ERROR: EVAVO doctor found a blocking environment problem.
    popd >nul
    exit /b 2
)

"%PYTHON%" "%ROOT%evavo.py" start
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    echo.
    "%PYTHON%" "%ROOT%evavo.py" status
)

popd >nul
exit /b %EXIT_CODE%
