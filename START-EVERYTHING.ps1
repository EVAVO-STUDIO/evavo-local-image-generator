# Compatibility shim for the historical all-in-one launcher.
# It no longer hardcodes a ComfyUI checkout, opens a visible service console,
# probes obsolete endpoints, or starts surprise autonomous generation jobs.

param(
    [ValidateSet("Start", "Monitor", "Full")]
    [string]$Mode = "Full",
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

Write-Host "START-EVERYTHING.ps1 is a compatibility shim for the canonical EVAVO controller." -ForegroundColor Yellow
Write-Host "Historical automatic generation and hardcoded C:\AI\ComfyUI startup have been retired." -ForegroundColor Yellow

switch ($Mode) {
    "Full" {
        & (Join-Path $PSScriptRoot "UPDATE-AND-VERIFY-EVAVO.ps1")
        exit $LASTEXITCODE
    }
    "Start" {
        & $python (Join-Path $PSScriptRoot "evavo.py") start --no-mock
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $python (Join-Path $PSScriptRoot "evavo.py") status
        exit $LASTEXITCODE
    }
    "Monitor" {
        & $python (Join-Path $PSScriptRoot "evavo.py") start --no-mock
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $python (Join-Path $PSScriptRoot "monitor-evavo.py") --interval $Interval
        exit $LASTEXITCODE
    }
}
