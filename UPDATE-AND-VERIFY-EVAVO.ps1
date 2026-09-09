# EVAVO Local Image Generator - update, install, validate, configure agents and verify
# Safe by default: refuses to overwrite local Git changes and only fast-forwards main.

param(
    [switch]$SkipDependencies,
    [switch]$SkipAgentConfiguration,
    [switch]$SkipComfyUIProvision,
    [int]$McpPort = 8765
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail([string]$Message, [int]$Code = 1) {
    Write-Error $Message
    exit $Code
}

if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    Fail "MCP port must be between 1 and 65535." 2
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

Write-Host "Running provisioning/runtime safety tests..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-provisioning.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Provisioning/runtime safety tests failed." 3
}

Write-Host "Running backend automation/MCP file-boundary tests..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-backend-automation.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Backend automation/MCP file-boundary tests failed." 3
}

Write-Host "Running Claude/ChatGPT MCP transport validation..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-agent-integration.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Agent/MCP integration tests failed." 3
}

Write-Host "Running EVAVO bootstrap..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") bootstrap --skip-pull
$code = $LASTEXITCODE
if ($code -ne 0) {
    Fail "EVAVO bootstrap failed with exit code $code. Review doctor output and .evavo logs." $code
}

if (-not $SkipAgentConfiguration) {
    Write-Host "Installing/updating Claude Desktop stdio MCP configuration..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-CLAUDE-MCP.ps1")
    if ($LASTEXITCODE -ne 0) {
        Fail "Claude MCP configuration failed." 3
    }

    Write-Host "Installing/updating per-user HTTP MCP autostart..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-AGENT-MCP-AUTOSTART.ps1") -Port $McpPort
    if ($LASTEXITCODE -ne 0) {
        Fail "HTTP MCP autostart installation failed." 3
    }
}

Write-Host "Running final agent doctor with safe repair enabled..." -ForegroundColor Cyan
$doctorArgs = @((Join-Path $PSScriptRoot "agent-doctor.py"), "--repair", "--mcp-port", "$McpPort")
if (-not $SkipComfyUIProvision) {
    $doctorArgs += "--provision"
}
& $python @doctorArgs
if ($LASTEXITCODE -ne 0) {
    Fail "Agent doctor found a blocking configuration problem. Configure a checkpoint source/shared model root if required, then rerun." 3
}

Write-Host "Running final backend status..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") status
if ($LASTEXITCODE -ne 0) {
    Fail "Final backend status failed." 3
}

Write-Host ""
Write-Host "EVAVO workstation setup completed." -ForegroundColor Green
Write-Host "  Dependencies: installed/validated" -ForegroundColor Green
Write-Host "  Provisioning/runtime safety tests: passed" -ForegroundColor Green
Write-Host "  Backend repair/file-boundary tests: passed" -ForegroundColor Green
Write-Host "  Operational tests: passed" -ForegroundColor Green
Write-Host "  MCP negotiation/generation/model-inventory tests: passed" -ForegroundColor Green
if (-not $SkipAgentConfiguration) {
    Write-Host "  Claude stdio MCP: installed/updated" -ForegroundColor Green
    Write-Host "  HTTP MCP autostart: installed and started" -ForegroundColor Green
}
if (-not $SkipComfyUIProvision) {
    Write-Host "  ComfyUI provisioning: enabled when missing" -ForegroundColor Green
}
Write-Host "  Agent doctor: real renderer + checkpoint + model inventory checked" -ForegroundColor Green
Write-Host ""
Write-Host "Claude: restart Claude Desktop so it reloads its MCP configuration." -ForegroundColor Yellow
Write-Host "Local HTTP MCP endpoint: http://127.0.0.1:$McpPort/mcp" -ForegroundColor Green
Write-Host "Native ComfyUI is reused, auto-started, or provisioned when missing." -ForegroundColor Green
exit 0
