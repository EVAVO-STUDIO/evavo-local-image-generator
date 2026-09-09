# Stop only the configured EVAVO OpenAI Secure MCP Tunnel profile.
# This script does not require or expose the runtime API key.

param(
    [string]$Profile,
    [switch]$RemoveAutostart
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$statePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
if (-not (Test-Path $statePath)) {
    if ($RemoveAutostart) {
        & (Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1") -Uninstall
    }
    Write-Host "ChatGPT tunnel state is not configured; nothing to stop." -ForegroundColor Green
    exit 0
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
    throw "Tunnel profile is missing or invalid."
}

$binary = [string]$state.tunnel_client
if (-not $binary -or -not (Test-Path $binary)) {
    $binary = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client.exe"
}
if (-not (Test-Path $binary)) {
    throw "Configured tunnel-client executable is missing; refusing process matching without the expected executable path."
}
$expectedBinary = (Resolve-Path $binary).Path

$metadataPath = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client-install.json"
if (-not (Test-Path $metadataPath)) {
    throw "Tunnel-client integrity metadata is missing. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1 before managing the tunnel."
}
try {
    $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
    $expectedHash = [string]$metadata.binary_digest
}
catch {
    throw "Tunnel-client integrity metadata is invalid."
}
if ($expectedHash -notmatch '^[0-9a-f]{64}$') {
    throw "Tunnel-client integrity metadata does not contain a valid SHA-256."
}
$actualHash = (Get-FileHash -Path $expectedBinary -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Tunnel-client executable integrity check failed. Refusing to stop a process using untrusted local metadata."
}

$escapedProfile = [regex]::Escape($Profile)
$candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        ([string]$_.Name -ieq "tunnel-client.exe") -and
        ([string]$_.CommandLine -match "\brun\b") -and
        ([string]$_.CommandLine -match "--profile\s+(`"|')?$escapedProfile(`"|')?(\s|$)")
    }

if (-not $candidates) {
    Write-Host "Tunnel profile '$Profile' is not running." -ForegroundColor Green
}
else {
    foreach ($process in @($candidates)) {
        $pidValue = [int]$process.ProcessId
        $executablePath = [string]$process.ExecutablePath
        if (-not $executablePath) {
            throw "Tunnel PID $pidValue does not expose ExecutablePath; refusing to stop it without exact executable identity."
        }
        try {
            $resolvedProcessBinary = (Resolve-Path $executablePath).Path
        }
        catch {
            throw "Tunnel PID $pidValue executable path cannot be resolved; refusing to stop it."
        }
        if (-not [string]::Equals($resolvedProcessBinary, $expectedBinary, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Tunnel PID $pidValue uses '$resolvedProcessBinary', not EVAVO's verified '$expectedBinary'. Refusing to stop it."
        }
        Stop-Process -Id $pidValue -Force -ErrorAction Stop
        Write-Host "Stopped EVAVO ChatGPT tunnel '$Profile' PID $pidValue." -ForegroundColor Green
    }
}

if ($RemoveAutostart) {
    $installer = Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1"
    if (-not (Test-Path $installer)) {
        throw "ChatGPT tunnel autostart installer is missing: $installer"
    }
    & $installer -Uninstall -Profile $Profile
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove ChatGPT tunnel login autostart."
    }
}

exit 0
