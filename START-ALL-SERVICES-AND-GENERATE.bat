@echo off
setlocal enabledelayedexpansion

echo ===============================================================================
echo EVAVO COMPLETE GENERATION PIPELINE
echo ===============================================================================
echo.

REM Start ComfyUI in a new window
echo Starting ComfyUI server...
start "ComfyUI Server" cmd /k "cd /d C:\AI\ComfyUI && python main.py"
timeout /t 5 /nobreak

REM Start Ollama in a new window
echo Starting Ollama server...
start "Ollama Server" cmd /k "ollama serve"
timeout /t 3 /nobreak

REM Navigate to generation directory
cd /d C:\Gitrepos\evavo-local-image-generator

REM Run the complete generation
echo.
echo Starting generation script...
echo This will generate real images, videos, audio, text, particles, textures, and 3D models
echo.

python COMPLETE-MULTIMODAL-TEST.py

REM Copy outputs to beestation
echo.
echo Copying generated files to beestation...

if not exist "C:\Users\User\beestation\evavo-generation" (
    mkdir "C:\Users\User\beestation\evavo-generation"
)

REM Copy all output directories
for %%D in (evavo-images evavo-videos evavo-audio evavo-text evavo-particles evavo-models evavo-textures evavo-state) do (
    if exist "%%D" (
        echo Copying %%D to beestation...
        xcopy "%%D" "C:\Users\User\beestation\evavo-generation\%%D" /E /I /Y /Q
    )
)

echo.
echo ===============================================================================
echo GENERATION COMPLETE!
echo ===============================================================================
echo All generated content is now in: C:\Users\User\beestation\evavo-generation\
echo.
echo Generated directories:
echo   - evavo-images/      Generated images
echo   - evavo-videos/      Generated videos
echo   - evavo-audio/       Generated audio
echo   - evavo-text/        Generated text
echo   - evavo-particles/   Particle configurations
echo   - evavo-models/      3D models
echo   - evavo-textures/    PBR textures
echo   - evavo-state/       Generation metadata
echo.
pause
