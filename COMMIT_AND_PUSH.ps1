# Compatibility shim for safe EVAVO main-branch commit/push operations.
# Historical lock deletion, hardcoded paths and stale commit messages are retired.

param(
    [switch]$Push,
    [string]$Message = "chore(repo): update local EVAVO image-generator changes",
    [switch]$SkipVerify,
    [switch]$DryRun
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

$gitArgs = @((Join-Path $PSScriptRoot "safe_main_git.py"), "--message", $Message)
if (-not $Push) { $gitArgs += "--no-push" }
if ($SkipVerify) { $gitArgs += "--skip-verify" }
if ($DryRun) { $gitArgs += "--dry-run" }

& $python @gitArgs
exit $LASTEXITCODE
