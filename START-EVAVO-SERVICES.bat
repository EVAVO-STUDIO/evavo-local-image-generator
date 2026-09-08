@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM EVAVO Local Image Generator - deterministic Windows startup
REM Always resolves paths relative to this file and only terminates an
REM existing port-8188 process when its command line is this mock server.

set "ROOT=%~dp0"
set "ENDPOINT=http://127.0.0.1:8188"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python was not found. Install Python 3.10+ or create .venv.
        exit /b 2
    )
    set "PYTHON=python"
)

if not exist "%ROOT%mock-comfyui-server.py" (
    echo ERROR: Missing %ROOT%mock-comfyui-server.py
    exit /b 2
)
if not exist "%ROOT%evavo-wrapper.py" (
    echo ERROR: Missing %ROOT%evavo-wrapper.py
    exit /b 2
)
if not exist "%ROOT%monitor-evavo.py" (
    echo ERROR: Missing %ROOT%monitor-evavo.py
    exit /b 2
)

pushd "%ROOT%" >nul

echo.
echo ============================================================
echo EVAVO Local Image Generator - Service Startup
echo ============================================================
echo Python:   %PYTHON%
echo Endpoint: %ENDPOINT%
echo.

REM If port 8188 is already listening, only stop it when it is our mock server.
set "PORT_PID="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p=Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if($p){Write-Output $p}"`) do set "PORT_PID=%%P"

if defined PORT_PID (
    set "IS_EVAVO="
    for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=%PORT_PID%' -ErrorAction SilentlyContinue; if($p.CommandLine -match 'mock-comfyui-server\.py'){Write-Output 'YES'}"`) do set "IS_EVAVO=%%M"
    if /I "!IS_EVAVO!"=="YES" (
        echo Stopping existing EVAVO mock service on PID %PORT_PID%...
        taskkill /PID %PORT_PID% /F >nul 2>&1
        timeout /T 1 /NOBREAK >nul
    ) else (
        echo ERROR: Port 8188 is occupied by PID %PORT_PID%, but it is not the EVAVO mock service.
        echo        Stop or reconfigure that process before starting EVAVO.
        popd >nul
        exit /b 5
    )
)

echo Starting EVAVO mock ComfyUI service...
start "EVAVO ComfyUI Server" /min "%PYTHON%" "%ROOT%mock-comfyui-server.py"

set "READY=0"
for /L %%I in (1,1,20) do (
    "%PYTHON%" "%ROOT%monitor-evavo.py" --json > "%TEMP%\evavo-health.json" 2>nul
    if !errorlevel! equ 0 (
        set "READY=1"
        goto :ready
    )
    echo   readiness attempt %%I/20...
    timeout /T 1 /NOBREAK >nul
)

:ready
if "%READY%"=="1" (
    echo.
    echo ============================================================
    echo EVAVO services are ready on %ENDPOINT%
    echo ============================================================
    "%PYTHON%" "%ROOT%monitor-evavo.py"
    popd >nul
    exit /b 0
)

echo.
echo ERROR: EVAVO service did not become ready after 20 attempts.
echo Check the minimized "EVAVO ComfyUI Server" window and port 8188.
popd >nul
exit /b 3
