@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old shortcuts.
REM It repairs/provisions the real native image runtime and never launches
REM unrelated services or automatic generation jobs.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo START-ALL-SERVICES-AND-GENERATE.bat is a compatibility shim.

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --provision --skip-tests
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"

echo.
echo Native image backend ready. No implicit generation is performed.
echo Generate explicitly with: python evavo.py generate --prompts "your prompt" --project demo --wait

popd >nul
exit /b %CODE%
