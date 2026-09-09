# Start the optional loopback HTTP compatibility gateway.
# Production health requires native ComfyUI; deterministic mock fallback is not
# accepted by EVAVO-SERVICE-MANAGER.py.

param(
    [switch]$Monitor,
    [switch]$SkipInstall,
    [switch]$SkipValidation,
    [int]$Interval = 5
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Interval -lt 1) {
    throw "-Interval must be at least 1 second."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python 3.10+ was not found."
    }
    $python = $command.Source
}

& $python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python failed to run."
}

if (-not $SkipInstall) {
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
}

if (-not $SkipValidation) {
    & $python (Join-Path $PSScriptRoot "verify-evavo.py") --require-powershell
    if ($LASTEXITCODE -ne 0) {
        throw "Repository structural verification failed."
    }
}

if (-not $env:EVAVO_GATEWAY_HOST) { $env:EVAVO_GATEWAY_HOST = "127.0.0.1" }
if (-not $env:EVAVO_GATEWAY_PORT) { $env:EVAVO_GATEWAY_PORT = "8000" }
if (-not $env:COMFYUI_ENDPOINT -and -not $env:EVAVO_COMFYUI_ENDPOINT) {
    $env:COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
}

$manager = Join-Path $PSScriptRoot "EVAVO-SERVICE-MANAGER.py"
if ($Monitor) {
    & $python $manager monitor --interval $Interval
    exit $LASTEXITCODE
}

& $python $manager start
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "EVAVO native-image gateway is ready." -ForegroundColor Green
Write-Host "Gateway: http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)" -ForegroundColor Green
Write-Host "Docs:    http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)/docs" -ForegroundColor Green
Write-Host "Health:  http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)/health" -ForegroundColor Green
