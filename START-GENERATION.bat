@echo off
setlocal EnableExtensions

REM Compatibility shim for historical START-GENERATION.bat.
REM No hardcoded repo path, no pause, and no implicit multimodal generation.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%ROOT%legacy_image_cli.py" %*
set "CODE=%errorlevel%"
popd >nul
exit /b %CODE%
