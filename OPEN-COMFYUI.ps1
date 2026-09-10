param(
    [ValidateRange(1, 3600)]
    [int]$WaitSeconds = 90
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "EVAVO .venv is not ready. Run .\UPDATE-AND-VERIFY-EVAVO.ps1 first."
}

& $python (Join-Path $PSScriptRoot "evavo.py") open-ui --wait $WaitSeconds
exit $LASTEXITCODE
