# Install/remove current-user Windows login autostart for the EVAVO ChatGPT tunnel.
# The generated Startup command never contains CONTROL_PLANE_API_KEY. The key is
# loaded at runtime from the process environment or the current-user DPAPI store.

param(
    [switch]$Uninstall,
    [string]$Profile,
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:APPDATA) {
    throw "APPDATA is unavailable; current-user Windows Startup cannot be configured."
}

$statePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$launcher = Join-Path $startupDir "EVAVO-ChatGPT-MCP-Tunnel.cmd"

if ($Uninstall) {
    Remove-Item -Path $launcher -Force -ErrorAction SilentlyContinue
    Write-Host "Removed EVAVO ChatGPT tunnel login autostart." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $statePath)) {
    throw "ChatGPT tunnel is not configured. Run INSTALL-CHATGPT-MCP-TUNNEL.ps1 first."
}
try {
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
}
catch {
    throw "ChatGPT tunnel state is invalid: $statePath"
}

if (-not $Profile) {
    $Profile = [string]$state.profile
}
if (-not $Profile -or $Profile -notmatch '^[A-Za-z0-9._-]+$') {
    throw "A valid tunnel profile is required. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1 if needed."
}

$starter = Join-Path $PSScriptRoot "START-CHATGPT-MCP-TUNNEL.ps1"
if (-not (Test-Path $starter)) {
    throw "Missing START-CHATGPT-MCP-TUNNEL.ps1"
}
$binary = [string]$state.tunnel_client
if (-not $binary -or -not (Test-Path $binary)) {
    $binary = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client.exe"
}
if (-not (Test-Path $binary)) {
    throw "OpenAI tunnel-client is not installed. Run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}

$keyAvailable = [bool]$env:CONTROL_PLANE_API_KEY
$keyPath = $null
if ($env:LOCALAPPDATA) {
    $keyPath = Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi"
}
if (-not $keyAvailable -and (-not $keyPath -or -not (Test-Path $keyPath))) {
    throw "Tunnel autostart requires a runtime key. Set CONTROL_PLANE_API_KEY temporarily and run SAVE-CHATGPT-TUNNEL-KEY.ps1 -FromEnvironment, or run SAVE-CHATGPT-TUNNEL-KEY.ps1 interactively."
}

function Get-ProfileTunnelProcess([string]$Name) {
    $escaped = [regex]::Escape($Name)
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ([string]$_.Name -ieq "tunnel-client.exe") -and
            ([string]$_.CommandLine -match "\brun\b") -and
            ([string]$_.CommandLine -match "--profile\s+(`"|')?$escaped(`"|')?(\s|$)")
        } |
        Select-Object -First 1
}

$existing = Get-ProfileTunnelProcess $Profile
if ($existing) {
    Write-Host "OpenAI tunnel-client profile '$Profile' is already running (PID $($existing.ProcessId))." -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
$repo = (Resolve-Path $PSScriptRoot).Path
if ($repo.Contains('"') -or $starter.Contains('"')) {
    throw "Repository path contains an unsupported quote character."
}
$escapedRepo = $repo.Replace('%', '%%')
$escapedStarter = $starter.Replace('%', '%%')
$escapedProfile = $Profile.Replace('%', '%%')
$cmd = @"
@echo off
cd /d "$escapedRepo"
start "EVAVO ChatGPT MCP Tunnel" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$escapedStarter" -Profile "$escapedProfile" -SkipDoctor
"@
Set-Content -Path $launcher -Value $cmd -Encoding ASCII

Write-Host "Installed EVAVO ChatGPT tunnel login autostart:" -ForegroundColor Green
Write-Host "  $launcher" -ForegroundColor Green
Write-Host "Profile: $Profile" -ForegroundColor Green
Write-Host "No plaintext OpenAI API key is stored in the Startup command." -ForegroundColor Green

if (-not $existing) {
    if (-not $SkipDoctor) {
        Write-Host "Validating tunnel before background start..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -Profile $Profile -RequireRuntimeKey
        if ($LASTEXITCODE -ne 0) {
            throw "ChatGPT tunnel doctor failed; autostart file was installed but the tunnel was not started."
        }
    }

    Write-Host "Starting tunnel profile '$Profile' now in a hidden process..." -ForegroundColor Cyan
    $quotedStarter = '"' + $starter.Replace('"', '\"') + '"'
    $argumentLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $quotedStarter -Profile $Profile -SkipDoctor"
    Start-Process -FilePath "powershell.exe" -ArgumentList $argumentLine -WorkingDirectory $repo -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        $existing = Get-ProfileTunnelProcess $Profile
    } while (-not $existing -and (Get-Date) -lt $deadline)
    if (-not $existing) {
        throw "tunnel-client profile '$Profile' did not remain running within 30 seconds. Run START-CHATGPT-MCP-TUNNEL.ps1 manually for diagnostics."
    }
    Write-Host "Tunnel profile '$Profile' is running (PID $($existing.ProcessId))." -ForegroundColor Green
}

exit 0
