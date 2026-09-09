@echo off
setlocal EnableExtensions

REM EVAVO Local Image Generator - strict native Windows launcher.
REM This filename no longer starts the deterministic mock fallback; real service
REM readiness means native ComfyUI plus the active workflow/model contract.

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
echo EVAVO Local Image Generator - Native Service Startup
echo ============================================================
echo Python: %PYTHON%
echo.

"%PYTHON%" "%ROOT%evavo.py" doctor
if errorlevel 2 (
    set "CODE=%errorlevel%"
    echo ERROR: EVAVO doctor found a blocking repository/environment problem.
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --provision --skip-tests
if errorlevel 1 (
    set "CODE=%errorlevel%"
    echo ERROR: Real native image-generation readiness could not be established.
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"
popd >nul
exit /b %CODE%
