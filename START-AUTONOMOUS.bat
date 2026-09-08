@echo off
setlocal EnableExtensions

REM Compatibility shim retained for old EVAVO shortcuts.
REM The former version invoked MASTER-AUTOMATION-CONTROLLER.ps1 and paused in
REM console windows. Agent setup and lifecycle now live in the canonical tools.

set "ROOT=%~dp0"
pushd "%ROOT%" >nul
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo START-AUTONOMOUS.bat now validates the canonical EVAVO agent stack.

"%PYTHON%" "%ROOT%agent-doctor.py" --repair
if errorlevel 1 (
    set "CODE=%errorlevel%"
    popd >nul
    exit /b %CODE%
)

"%PYTHON%" "%ROOT%evavo.py" status
set "CODE=%errorlevel%"

echo.
echo EVAVO agent backend is ready.
echo Claude uses stdio MCP; local HTTP MCP uses http://127.0.0.1:8765/mcp.

popd >nul
exit /b %CODE%
