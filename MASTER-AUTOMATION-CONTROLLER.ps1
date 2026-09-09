# Compatibility shim for the historical EVAVO master automation controller.
# The old implementation independently killed Python processes, launched a
# hardcoded ComfyUI checkout, generated content automatically, and registered a
# Windows Scheduled Task. Those responsibilities now belong to the canonical
# identity-safe controller, verifier, agent doctor and opt-in login installers.

param(
    [ValidateSet("Full", "Monitor", "Service", "Test", "Status")]
    [string]$Mode = "Full",
    [int]$MaxRestarts = 3,
    [int]$HealthCheckInterval = 30
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Retained only for command-line compatibility with old shortcuts.
if ($MaxRestarts -lt 0) { throw "-MaxRestarts cannot be negative." }
if ($HealthCheckInterval -lt 1) { throw "-HealthCheckInterval must be at least 1 second." }

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { throw "Python 3.10+ was not found." }
    $python = $command.Source
}

Write-Host "MASTER-AUTOMATION-CONTROLLER.ps1 is now a compatibility shim." -ForegroundColor Yellow
Write-Host "Unsafe process killing, hardcoded service launch, automatic generation, and Scheduled Task creation are retired." -ForegroundColor Yellow

switch ($Mode) {
    "Full" {
        & (Join-Path $PSScriptRoot "UPDATE-AND-VERIFY-EVAVO.ps1")
        exit $LASTEXITCODE
    }
    "Test" {
        & $python (Join-Path $PSScriptRoot "evavo.py") verify --full --require-powershell
        exit $LASTEXITCODE
    }
    "Service" {
        & $python (Join-Path $PSScriptRoot "evavo.py") start --no-mock
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $python (Join-Path $PSScriptRoot "evavo.py") status
        exit $LASTEXITCODE
    }
    "Status" {
        & $python (Join-Path $PSScriptRoot "evavo.py") status
        exit $LASTEXITCODE
    }
    "Monitor" {
        & $python (Join-Path $PSScriptRoot "evavo.py") start --no-mock
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $python (Join-Path $PSScriptRoot "monitor-evavo.py") --interval $HealthCheckInterval
        exit $LASTEXITCODE
    }
}
