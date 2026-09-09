@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old EVAVO shortcuts.
REM It now repairs/provisions the real image runtime and never starts hidden
REM multimodal jobs or unrelated services.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo START-AUTONOMOUS.bat now validates the canonical EVAVO agent stack.

"%PYTHON%" "%ROOT%agent-doctor.py" --repair --provision --skip-tests
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"

echo.
echo EVAVO native image backend is ready.
echo Claude uses local stdio MCP. ChatGPT uses the outbound OpenAI Secure MCP Tunnel.

popd >nul
exit /b %CODE%
