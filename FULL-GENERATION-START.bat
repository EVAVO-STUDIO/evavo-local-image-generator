@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old shortcuts.
REM It repairs/provisions native ComfyUI and does not start unrelated services,
REM copy folders, or generate content automatically.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo FULL-GENERATION-START.bat now uses the canonical EVAVO native-image lifecycle.

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --provision --skip-tests
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"

echo.
echo Native image backend ready. Generate explicitly with:
echo   python evavo.py generate --prompts "your prompt" --project demo --wait

popd >nul
exit /b %CODE%
