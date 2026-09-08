@echo off
REM Start EVAVO services on Windows
REM Kills existing ComfyUI process and starts mock server

setlocal enabledelayedexpansion

echo.
echo ===============================================
echo EVAVO Local Image Generator - Service Startup
echo ===============================================
echo.

echo Checking for existing ComfyUI processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq ComfyUI*" 2>nul

echo Waiting for port 8188 to be free...
timeout /T 2 /NOBREAK

echo Starting mock ComfyUI server...
start "ComfyUI Server" cmd /k python mock-comfyui-server.py

echo Verifying server is responding...
timeout /T 3 /NOBREAK

for /L %%i in (1,1,10) do (
    curl -s http://127.0.0.1:8188/system >nul 2>&1
    if !errorlevel! equ 0 (
        echo.
        echo ===============================================
        echo ✓ ComfyUI Server is running on port 8188
        echo ✓ EVAVO services ready
        echo ===============================================
        echo.
        goto :success
    )
    timeout /T 1 /NOBREAK
)

echo.
echo ✗ Failed to start server. Check port 8188.
echo.
goto :end

:success
echo Services started successfully.
echo.

:end
timeout /T 5
endlocal
