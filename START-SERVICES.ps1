# Compatibility startup shim for old EVAVO shortcuts.
# The former version opened persistent PowerShell windows for ComfyUI, Ollama
# and Kokoro. Image-generation lifecycle ownership now belongs to the canonical
# agent doctor/runtime manager.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python 3.10+ was not found." }
    $python = $cmd.Source
}

Write-Host "START-SERVICES.ps1 is a compatibility shim; using canonical EVAVO lifecycle." -ForegroundColor Yellow
& $python (Join-Path $PSScriptRoot "agent-doctor.py") --repair --provision --skip-tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $PSScriptRoot "evavo.py") status
exit $LASTEXITCODE
