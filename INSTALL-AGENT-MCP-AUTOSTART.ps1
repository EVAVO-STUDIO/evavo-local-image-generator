# Install or remove EVAVO Streamable HTTP MCP startup for the current Windows user.
# Uses the per-user Startup folder; no administrator rights required.

param(
    [switch]$Uninstall,
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535."
}

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
$launcher = Join-Path $startupDir "EVAVO-Agent-MCP.cmd"

if ($Uninstall) {
    if (Test-Path $launcher) {
        Remove-Item -Force $launcher
        Write-Host "Removed EVAVO agent MCP autostart: $launcher" -ForegroundColor Green
    } else {
        Write-Host "EVAVO agent MCP autostart was not installed." -ForegroundColor Yellow
    }
    exit 0
}

$repo = (Resolve-Path $PSScriptRoot).Path
$script = Join-Path $repo "START-AGENT-MCP.ps1"
if (-not (Test-Path $script)) {
    throw "Missing START-AGENT-MCP.ps1"
}

$escapedRepo = $repo.Replace('"', '""')
$escapedScript = $script.Replace('"', '""')
$cmd = @"
@echo off
cd /d "$escapedRepo"
start "EVAVO Agent MCP" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$escapedScript" -Port $Port
"@
Set-Content -Path $launcher -Value $cmd -Encoding ASCII

Write-Host "Installed EVAVO agent MCP autostart:" -ForegroundColor Green
Write-Host "  $launcher"
Write-Host "It will expose http://127.0.0.1:$Port/mcp after Windows sign-in." -ForegroundColor Green
Write-Host "Starting it now..." -ForegroundColor Cyan
& $script -Port $Port
