# Compatibility shim retained for historical RUN-FULL-GENERATION.ps1 shortcuts.
# It now uses the shared image-only compatibility CLI and performs no unrelated
# service startup, automatic copying, or implicit generation.

param(
    [string]$Prompt,
    [string]$Project = "legacy_full_generation"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python 3.10+ was not found." }
    $python = $cmd.Source
}

$args = @((Join-Path $PSScriptRoot "legacy_image_cli.py"), "--repair", "--project", $Project)
if ($Prompt) {
    $args += @("--prompts", $Prompt)
}

& $python @args
exit $LASTEXITCODE
