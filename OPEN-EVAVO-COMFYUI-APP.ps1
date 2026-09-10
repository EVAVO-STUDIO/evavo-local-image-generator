param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8770
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "EVAVO .venv is not ready. Run UPDATE-AND-VERIFY-EVAVO.ps1 first."
}

& $python -c "from evavo_local_image_generator.local_app import ensure_local_control_app; import json; print(json.dumps(ensure_local_control_app(port=$Port), sort_keys=True))"
if ($LASTEXITCODE -ne 0) {
    throw "EVAVO local ComfyUI control app did not start."
}
