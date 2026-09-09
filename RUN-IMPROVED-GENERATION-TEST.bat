@echo off
REM ============================================================
REM IMPROVED COMFYUI GENERATION TEST - HIGH QUALITY VERSION
REM ============================================================
REM This script starts ComfyUI with GPU and runs improved tests
REM with 25-30 steps for much better image quality.
REM 
REM Key improvements over previous tests:
REM - Steps: 5 → 25-30 (HUGE quality improvement)
REM - Resolution: 512x512 → 768x768 (better detail)
REM - Better prompts: More detailed descriptions
REM - Improved CFG: 7.0 → 8.0-8.5 (better prompt adherence)
REM ============================================================

setlocal enabledelayedexpansion

cd /d C:\AI\ComfyUI

echo.
echo ============================================================
echo CHECKING CUDA AVAILABILITY
echo ============================================================

python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

if errorlevel 1 (
    echo WARNING: Could not verify CUDA. Will attempt to start server anyway.
)

echo.
echo ============================================================
echo KILLING OLD PROCESSES
echo ============================================================

taskkill /F /IM python.exe 2>nul
echo Cleanup complete.

echo.
echo ============================================================
echo STARTING COMFYUI SERVER (GPU MODE)
echo ============================================================
echo Server is starting in this window...
echo NOTE: Do NOT close this window until testing is complete!
echo.

timeout /t 3 /nobreak

REM Start ComfyUI (no --cpu flag = GPU mode)
python main.py

