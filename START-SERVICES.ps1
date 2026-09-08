# EVAVO Service Startup Script for PowerShell
# Starts ComfyUI, Ollama, and TTS services

Write-Host "================================" -ForegroundColor Green
Write-Host "EVAVO SERVICE STARTUP" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Start ComfyUI
Write-Host "1. Starting ComfyUI..." -ForegroundColor Yellow
try {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\AI\ComfyUI; python main.py" -WindowStyle Normal
    Write-Host "   [OK] ComfyUI starting..." -ForegroundColor Green
    Start-Sleep -Seconds 5
} catch {
    Write-Host "   [ERROR] Failed to start ComfyUI: $_" -ForegroundColor Red
}

# Start Ollama
Write-Host "2. Starting Ollama..." -ForegroundColor Yellow
try {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "ollama serve" -WindowStyle Normal
    Write-Host "   [OK] Ollama starting..." -ForegroundColor Green
    Start-Sleep -Seconds 3
} catch {
    Write-Host "   [ERROR] Failed to start Ollama: $_" -ForegroundColor Red
}

# Start Kokoro TTS (optional)
Write-Host "3. Starting TTS service (optional)..." -ForegroundColor Yellow
try {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\AI\Kokoro-FastAPI; python -m uvicorn kokoro:app --port 8000" -WindowStyle Normal
    Write-Host "   [OK] TTS service starting..." -ForegroundColor Green
} catch {
    Write-Host "   [SKIPPED] TTS service not available" -ForegroundColor Gray
}

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "Services Starting..." -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "ComfyUI:  http://127.0.0.1:8188" -ForegroundColor Cyan
Write-Host "Ollama:   http://127.0.0.1:11434" -ForegroundColor Cyan
Write-Host "TTS:      http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Waiting 10 seconds before running generation..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Run generation
Write-Host ""
Write-Host "Running generation..." -ForegroundColor Yellow
cd "C:\Gitrepos\evavo-local-image-generator"
python RUN-GENERATION.py

Write-Host ""
Write-Host "All done!" -ForegroundColor Green
