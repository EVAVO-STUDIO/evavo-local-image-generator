@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old shortcuts.
REM The former implementation opened persistent cmd windows, hardcoded
REM C:\AI\ComfyUI and user BeeStation paths, launched unrelated services and
REM generated/copyied multimodal assets automatically. That behavior is retired.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

where "%PYTHON%" >nul 2>&1
if errorlevel 1 (
    if not exist "%PYTHON%" (
        echo ERROR: Python 3.10+ was not found.
        popd >nul
        exit /b 2
    )
)

echo START-ALL-SERVICES-AND-GENERATE.bat is a compatibility shim.
echo Starting the canonical native EVAVO image-generation backend without extra consoles...

"%PYTHON%" "%ROOT%evavo.py" start --no-mock
if errorlevel 1 (
    popd >nul
    exit /b %errorlevel%
)

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --skip-tests
if errorlevel 1 (
    popd >nul
    exit /b %errorlevel%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "EXITCODE=%errorlevel%"

echo.
echo No automatic sample generation is run by this legacy shortcut anymore.
echo Use: python evavo.py generate --prompts "your prompt" --project demo --wait

popd >nul
exit /b %EXITCODE%
