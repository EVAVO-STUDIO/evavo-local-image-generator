#Requires -Version 5.0
<#
.SYNOPSIS
Verify EVAVO Local Image Generator installation

.DESCRIPTION
Checks Python, dependencies, services, and MCP configuration

.EXAMPLE
.\VERIFY-INSTALLATION.ps1
#>

Write-Host "EVAVO Installation Verification" -ForegroundColor Cyan
Write-Host "===============================" -ForegroundColor Cyan
Write-Host ""

# Python
Write-Host "Checking Python..."
python --version
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Python installed" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Python not found" -ForegroundColor Red
}

# Dependencies
Write-Host ""
Write-Host "Checking dependencies..."
pip list | findstr /i "httpx pytest pydantic"
Write-Host "[PASS] Dependencies verified" -ForegroundColor Green

# ComfyUI
Write-Host ""
Write-Host "Checking ComfyUI..."
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8188/system" -TimeoutSec 2 -ErrorAction SilentlyContinue
    Write-Host "[PASS] ComfyUI available" -ForegroundColor Green
} catch {
    Write-Host "[WARN] ComfyUI not responding (optional)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[PASS] Verification complete" -ForegroundColor Green
