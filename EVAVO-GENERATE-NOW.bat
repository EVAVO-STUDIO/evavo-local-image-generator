@echo off
setlocal EnableExtensions

REM Compatibility shim. Historical versions killed every python.exe process,
REM started ComfyUI/Ollama/Kokoro independently and claimed multimodal output.
REM Arguments are now forwarded to the canonical image-only compatibility CLI.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo EVAVO-GENERATE-NOW.bat now routes to the canonical native image pipeline.
echo Provide --prompts "..." or --examples explicitly.

"%PYTHON%" "%ROOT%legacy_image_cli.py" %*
set "CODE=%errorlevel%"
popd >nul
exit /b %CODE%
