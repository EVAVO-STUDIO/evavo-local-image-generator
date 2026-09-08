@echo off
title EVAVO Complete Generation Pipeline
color 0A

echo.
echo ============================================================================
echo EVAVO COMPLETE MULTI-MODAL GENERATION SYSTEM
echo ============================================================================
echo.

REM Kill any existing services
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Start ComfyUI in background
echo Starting ComfyUI (Image & Video Generation)...
start "" cmd /c "cd /d C:\AI\ComfyUI && python main.py"
timeout /t 4 /nobreak >nul

REM Start Ollama in background  
echo Starting Ollama (Text & LLM Generation)...
start "" cmd /c "ollama serve"
timeout /t 3 /nobreak >nul

REM Start TTS service in background
echo Starting TTS Service (Audio Synthesis)...
start "" cmd /c "cd /d C:\AI\Kokoro-FastAPI && python -m uvicorn kokoro:app --port 8000"
timeout /t 2 /nobreak >nul

REM Wait for services to initialize
echo.
echo Waiting for services to initialize... (15 seconds)
timeout /t 15 /nobreak

REM Run the generation
cd /d C:\Gitrepos\evavo-local-image-generator
echo.
echo Starting multi-modal content generation...
echo This will generate: Images, Videos, Audio, Text, 3D Models, Particles, and Textures
echo.

python RUN-GENERATION.py

REM Display completion message
echo.
echo ============================================================================
echo GENERATION COMPLETE!
echo ============================================================================
echo.
echo All generated content has been saved to:
echo C:\Users\User\beestation\evavo-generation\
echo.
echo Check these directories for your content:
echo   - evavo-images/    (Real images in all styles)
echo   - evavo-videos/    (Generated video clips)
echo   - evavo-audio/     (Speech synthesis and music)
echo   - evavo-text/      (Generated creative text)
echo   - evavo-particles/ (Particle system configs)
echo   - evavo-models/    (3D models in GLB format)
echo   - evavo-textures/  (PBR texture sets)
echo   - evavo-state/     (Generation metadata)
echo.
pause
