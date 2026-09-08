# EVAVO Local Image Generator - update, install, validate, start and verify
# Safe by default: refuses to overwrite local changes and only fast-forwards main.

param(
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail([string]$Message, [int]$Code = 1) {
    Write-Error $Message
    exit $Code
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git is not installed or not available on PATH." 2
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    Fail "Repository must be on branch main. Current branch: $branch" 2
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    Fail "Unable to inspect Git working tree." 2
}
if ($dirty) {
    Write-Host "Local changes detected:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    Fail "Refusing to overwrite local work. Commit or stash those changes first." 2
}

Write-Host "Updating EVAVO from origin/main..." -ForegroundColor Cyan
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    Fail "git pull --ff-only origin main failed." 3
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Fail "Python 3.10+ was not found." 2
    }
    $python = $pythonCommand.Source
}

Write-Host "Using Python: $python" -ForegroundColor Cyan
& $python --version
if ($LASTEXITCODE -ne 0) {
    Fail "Python failed to run." 2
}

if (-not $SkipDependencies) {
    Write-Host "Installing/updating EVAVO dependencies..." -ForegroundColor Cyan
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Fail "Dependency installation failed." 3
    }
}

Write-Host "Running EVAVO bootstrap..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") bootstrap --skip-pull
$code = $LASTEXITCODE
if ($code -ne 0) {
    Fail "EVAVO bootstrap failed with exit code $code. Review doctor output and .evavo\mock-service.log." $code
}

Write-Host "Running final backend status..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") status
if ($LASTEXITCODE -ne 0) {
    Fail "Final backend status failed." 3
}

Write-Host ""
Write-Host "EVAVO is updated, dependencies are installed, tests passed, and the backend is operational." -ForegroundColor Green
Write-Host "For a real file render, ensure native ComfyUI is running and use:" -ForegroundColor Green
Write-Host "  python generate-batch.py --prompts \"EVAVO smoke test\" --project smoke --wait" -ForegroundColor Green
exit 0
