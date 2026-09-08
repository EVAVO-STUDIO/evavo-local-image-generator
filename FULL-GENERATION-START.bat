@echo off
REM EVAVO Full Generation - Starts all services and runs complete generation

echo ========================================================================
echo  EVAVO MULTI-MODAL GENERATION SYSTEM
echo  Starting all services and running full content generation
echo ========================================================================
echo.

REM Start ComfyUI in background
echo Starting ComfyUI server...
start "ComfyUI Server" cmd /k "cd C:\AI\ComfyUI && python main.py"
timeout /t 5 /nobreak

REM Start Ollama in background  
echo Starting Ollama server...
start "Ollama Server" cmd /k "ollama serve"
timeout /t 3 /nobreak

REM Run full test generation
echo.
echo Running full 71-test generation suite...
echo This will generate images, videos, audio, text, particles, 3D models, and textures
echo Expected time: 45 minutes to 2 hours depending on GPU
echo.
cd /d C:\Gitrepos\evavo-local-image-generator
python COMPLETE-MULTIMODAL-TEST.py --execute

REM Copy to beestation
echo.
echo Copying all generated files to C:\Users\User\beestation\...
if not exist "C:\Users\User\beestation\evavo-generation" mkdir "C:\Users\User\beestation\evavo-generation"

for %%D in (evavo-images evavo-videos evavo-audio evavo-text evavo-particles evavo-models evavo-textures evavo-state evavo-generations) do (
    if exist "%%D" (
        echo Copying %%D...
        xcopy "%%D" "C:\Users\User\beestation\evavo-generation\%%D" /E /I /Y
    )
)

echo.
echo ========================================================================
echo GENERATION COMPLETE
echo All files copied to: C:\Users\User\beestation\evavo-generation\
echo ========================================================================
pause

