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

# Start it now without blocking this installer. The server itself remains a
# foreground process inside the spawned hidden PowerShell process so failures
# are not detached from their owning process tree.
Write-Host "Starting it now in a hidden process..." -ForegroundColor Cyan
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-WindowStyle", "Hidden",
    "-File", $script,
    "-Port", "$Port"
)
Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden | Out-Null

$deadline = (Get-Date).AddSeconds(20)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(300) -and $client.Connected) {
            $client.EndConnect($iar)
            $client.Close()
            $ready = $true
            break
        }
        $client.Close()
    } catch {
    }
    Start-Sleep -Milliseconds 250
}

if (-not $ready) {
    throw "EVAVO MCP did not begin listening on port $Port within 20 seconds. Run START-AGENT-MCP.ps1 manually for diagnostics."
}

Write-Host "EVAVO MCP is listening at http://127.0.0.1:$Port/mcp" -ForegroundColor Green
