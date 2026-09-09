# Compatibility shim retained for old EVAVO shortcuts.
# Destructive .git deletion/reinitialization and Git identity rewriting are retired.

param(
    [string]$Message = "chore(repo): update local EVAVO image-generator changes",
    [switch]$NoPush,
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

Write-Host "COMPLETE_EVAVO_GIT_COMMIT.ps1 is now a safe compatibility shim." -ForegroundColor Yellow
Write-Host "It will not delete/recreate .git, alter Git identity, force-push, or repair divergent history." -ForegroundColor Yellow

$gitArgs = @((Join-Path $PSScriptRoot "safe_main_git.py"), "--message", $Message)
if ($NoPush) { $gitArgs += "--no-push" }
if ($SkipVerify) { $gitArgs += "--skip-verify" }
if ($DryRun) { $gitArgs += "--dry-run" }

& $python @gitArgs
exit $LASTEXITCODE
