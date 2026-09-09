# Historical compatibility helper.
# The EVAVO-STUDIO/evavo-local-image-generator repository already exists.
# This script now validates the current local origin instead of creating,
# changing visibility, replacing remotes, or pushing implicitly.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git was not found on PATH."
}

$root = (& git rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $root) {
    throw "This directory is not an active Git worktree."
}

$expectedRoot = (Resolve-Path $PSScriptRoot).Path
$actualRoot = (Resolve-Path $root).Path
if ($actualRoot -ne $expectedRoot) {
    throw "Active Git worktree root is '$actualRoot', expected '$expectedRoot'."
}

$origin = (& git remote get-url origin 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $origin) {
    throw "origin remote is not configured. Do not auto-create/replace it; configure the reviewed repository URL explicitly."
}

if ($origin -notmatch 'github\.com[/:]EVAVO-STUDIO/evavo-local-image-generator(?:\.git)?$') {
    throw "origin points to an unexpected repository: $origin"
}

Write-Host "EVAVO GitHub repository is already configured correctly." -ForegroundColor Green
Write-Host "Worktree: $actualRoot"
Write-Host "Origin:   $origin"
Write-Host "No repository creation, visibility change, remote rewrite, commit, or push was performed." -ForegroundColor Green
exit 0
