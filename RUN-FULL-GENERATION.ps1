# EVAVO Complete Multi-Modal Generation - Full Automation
# This script starts all services and runs comprehensive generation tests

Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "EVAVO COMPLETE MULTI-MODAL AI GENERATION - FULL AUTOMATION" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

$ProjectRoot = "C:\Gitrepos\evavo-local-image-generator"
$ComfyUIPath = "C:\AI\ComfyUI"
$OutputPath = "$ProjectRoot\evavo-generations"

# Create output directories
Write-Host "`nPreparing output directories..." -ForegroundColor Yellow
@("evavo-images", "evavo-videos", "evavo-audio", "evavo-text", "evavo-particles", "evavo-models", "evavo-textures", "evavo-state", "evavo-logs") | ForEach-Object {
    $dir = "$ProjectRoot\$_"
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Write-Host "  ✓ $_ directory ready" -ForegroundColor Green
}

# Start ComfyUI in background
Write-Host "`n▶ Starting ComfyUI (Image & Video Generation)..." -ForegroundColor Yellow
if (Test-Path "$ComfyUIPath\main.py") {
    Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory $ComfyUIPath -WindowStyle Minimized -PassThru | Out-Null
    Write-Host "  ✓ ComfyUI starting..." -ForegroundColor Green
    Write-Host "  Waiting 15 seconds for ComfyUI to initialize..." -ForegroundColor Gray
    Start-Sleep -Seconds 15
    
    # Verify ComfyUI is running
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8188/system_stats" -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "  ✓ ComfyUI is running and responsive" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠ ComfyUI may still be loading..." -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✗ ComfyUI not found at $ComfyUIPath" -ForegroundColor Red
}

# Start Ollama in background
Write-Host "`n▶ Starting Ollama (Text Generation)..." -ForegroundColor Yellow
$ollamaExists = $null -ne (Get-Command ollama -ErrorAction SilentlyContinue)
if ($ollamaExists) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized -PassThru | Out-Null
    Write-Host "  ✓ Ollama starting..." -ForegroundColor Green
    Write-Host "  Waiting 10 seconds for Ollama to initialize..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
    
    # Verify Ollama is running
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "  ✓ Ollama is running and responsive" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠ Ollama may still be loading..." -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ Ollama not found in PATH" -ForegroundColor Yellow
}

# Run comprehensive multi-modal test suite
Write-Host "`n▶ Starting Comprehensive Multi-Modal Generation Test Suite..." -ForegroundColor Yellow
Write-Host "  This will generate:" -ForegroundColor Gray
Write-Host "    • 45 images across 15 styles and 3 quality levels" -ForegroundColor Gray
Write-Host "    • 3 cinematic videos with different motion types" -ForegroundColor Gray
Write-Host "    • 6 audio files (speech synthesis + music)" -ForegroundColor Gray
Write-Host "    • 3 AI-generated text documents" -ForegroundColor Gray
Write-Host "    • 4 particle system configurations" -ForegroundColor Gray
Write-Host "    • 6 3D models in GLB format" -ForegroundColor Gray
Write-Host "    • 16 PBR texture files (4 materials × 4 maps)" -ForegroundColor Gray
Write-Host "  Expected duration: 45 minutes to 2 hours" -ForegroundColor Gray

cd $ProjectRoot
python COMPLETE-MULTIMODAL-TEST.py --execute 2>&1 | Tee-Object -FilePath "$ProjectRoot\evavo-logs\generation-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

Write-Host "`n═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "GENERATION COMPLETE" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

Write-Host "`nGenerated files are in:" -ForegroundColor Yellow
Write-Host "  📁 evavo-images/      - All generated images" -ForegroundColor Green
Write-Host "  📁 evavo-videos/      - Generated videos" -ForegroundColor Green
Write-Host "  📁 evavo-audio/       - Generated audio files" -ForegroundColor Green
Write-Host "  📁 evavo-text/        - Generated text" -ForegroundColor Green
Write-Host "  📁 evavo-particles/   - Particle configs" -ForegroundColor Green
Write-Host "  📁 evavo-models/      - 3D models" -ForegroundColor Green
Write-Host "  📁 evavo-textures/    - PBR textures" -ForegroundColor Green
Write-Host "  📁 evavo-state/       - Quality metrics & results" -ForegroundColor Green

Write-Host "`nPress any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
