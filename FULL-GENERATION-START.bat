@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old shortcuts.
REM The former implementation opened persistent ComfyUI/Ollama consoles,
REM executed legacy multimodal generation and copied to hardcoded user paths.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo FULL-GENERATION-START.bat now uses the canonical EVAVO image-generation lifecycle.

"%PYTHON%" "%ROOT%evavo.py" start --no-mock
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --skip-tests
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"

echo.
echo No automatic multimodal generation or BeeStation copy is performed anymore.
echo Generate explicitly with:
echo   python evavo.py generate --prompts "your prompt" --project demo --wait

popd >nul
exit /b %CODE%
