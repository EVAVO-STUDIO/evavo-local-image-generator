# Compatibility shim retained for old EVAVO shortcuts.
# The former script started ComfyUI/Ollama in separate processes, generated
# unrelated modalities automatically and paused for keyboard input.

param(
    [string]$Prompt,
    [string]$Project = "legacy_full_generation"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Python 3.10+ was not found."
    }
    $python = $cmd.Source
}

Write-Host "RUN-FULL-GENERATION.ps1 is now a compatibility shim for native EVAVO image generation." -ForegroundColor Yellow

& $python (Join-Path $PSScriptRoot "evavo.py") start --no-mock
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $python (Join-Path $PSScriptRoot "agent-doctor.py") --repair --skip-tests
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Prompt) {
    & $python (Join-Path $PSScriptRoot "evavo.py") generate --prompts $Prompt --project $Project --wait
    exit $LASTEXITCODE
}

Write-Host "Backend ready. No implicit generation is performed." -ForegroundColor Green
Write-Host "To render now:" -ForegroundColor Green
Write-Host "  .\RUN-FULL-GENERATION.ps1 -Prompt 'your prompt' -Project demo" -ForegroundColor Green
exit 0
