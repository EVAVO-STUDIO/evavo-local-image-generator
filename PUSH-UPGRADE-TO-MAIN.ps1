# Compatibility shim for safe EVAVO main-branch commits and pushes.
# The historical upgrade-archive extraction path is retired because it could
# overwrite current source and Git metadata with stale milestone contents.

param(
    [string]$Message = "chore(repo): update local EVAVO image-generator changes",
    [switch]$SkipVerify,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python 3.10+ was not found." }
    $python = $cmd.Source
}

$gitArgs = @((Join-Path $PSScriptRoot "safe_main_git.py"), "--message", $Message)
if ($SkipVerify) { $gitArgs += "--skip-verify" }
if ($DryRun) { $gitArgs += "--dry-run" }

& $python @gitArgs
exit $LASTEXITCODE
