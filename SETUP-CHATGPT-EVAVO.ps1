# One-command interactive setup for ChatGPT -> EVAVO through OpenAI Secure MCP Tunnel.
# Secrets are collected as SecureString and persisted only through Windows
# current-user DPAPI. The runtime key is never passed on a process command line.

param(
    [string]$TunnelId = $env:EVAVO_OPENAI_TUNNEL_ID,
    [string]$Profile = "evavo-chatgpt",
    [int]$McpPort = 8765,
    [switch]$SessionOnly,
    [switch]$SkipFinalDoctor
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    throw "MCP port must be between 1 and 65535."
}
if (-not $Profile -or $Profile -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Tunnel profile must contain only letters, digits, '.', '_' or '-'."
}

$statePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
if (-not $TunnelId -and (Test-Path $statePath)) {
    try {
        $state = Get-Content $statePath -Raw | ConvertFrom-Json
        $TunnelId = [string]$state.tunnel_id
    }
    catch {
        Write-Host "Existing tunnel state is invalid; a valid tunnel ID will be required." -ForegroundColor Yellow
    }
}

if (-not $TunnelId) {
    $TunnelId = (Read-Host "OpenAI Secure MCP Tunnel ID (tunnel_<32 lowercase hex>)").Trim()
}
if ($TunnelId -notmatch '^tunnel_[0-9a-f]{32}$') {
    throw "Tunnel ID must match tunnel_<32 lowercase hexadecimal characters>."
}

$installer = Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL.ps1"
$keySaver = Join-Path $PSScriptRoot "SAVE-CHATGPT-TUNNEL-KEY.ps1"
$autostart = Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1"
$doctor = Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1"
$starter = Join-Path $PSScriptRoot "START-CHATGPT-MCP-TUNNEL.ps1"
foreach ($required in @($installer, $keySaver, $autostart, $doctor, $starter)) {
    if (-not (Test-Path $required)) {
        throw "Required ChatGPT tunnel script is missing: $required"
    }
}

# Install/refresh the verified tunnel-client binary and profile first. Doctor is
# deferred until after a key is available.
& $installer -TunnelId $TunnelId -Profile $Profile -McpPort $McpPort -SkipDoctor
if ($LASTEXITCODE -ne 0) {
    throw "ChatGPT tunnel profile installation failed."
}

$secureKeyPath = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi" } else { $null }
$hasDpapiKey = $secureKeyPath -and (Test-Path $secureKeyPath)
$hasEnvironmentKey = [bool]$env:CONTROL_PLANE_API_KEY

if ($SessionOnly) {
    if (-not $hasEnvironmentKey) {
        throw "-SessionOnly requires CONTROL_PLANE_API_KEY in the current process environment; the wizard will not turn an interactive secret into plaintext environment state."
    }
    Write-Host "Starting session-only ChatGPT tunnel; runtime key will not be persisted by EVAVO." -ForegroundColor Cyan
    & $starter -Profile $Profile -McpPort $McpPort
    exit $LASTEXITCODE
}

if (-not $hasDpapiKey) {
    if ($hasEnvironmentKey) {
        Write-Host "Persisting the current process runtime key with Windows current-user DPAPI..." -ForegroundColor Cyan
        & $keySaver -FromEnvironment
    }
    else {
        Write-Host "No persistent runtime key is stored. You will be prompted securely now." -ForegroundColor Cyan
        & $keySaver
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to store the ChatGPT tunnel runtime key with Windows DPAPI."
    }
}

Write-Host "Installing/starting persistent ChatGPT tunnel login autostart..." -ForegroundColor Cyan
& $autostart -Profile $Profile -SkipDoctor
if ($LASTEXITCODE -ne 0) {
    throw "ChatGPT tunnel login autostart installation failed."
}

if (-not $SkipFinalDoctor) {
    Write-Host "Running final local tunnel readiness check..." -ForegroundColor Cyan
    & $doctor -Profile $Profile -RequireRuntimeKey -RequireRunning
    if ($LASTEXITCODE -ne 0) {
        throw "ChatGPT tunnel local readiness check failed."
    }
}

Write-Host "" 
Write-Host "EVAVO ChatGPT tunnel setup is complete for the local workstation." -ForegroundColor Green
Write-Host "Profile: $Profile" -ForegroundColor Green
Write-Host "Private MCP target: http://127.0.0.1:$McpPort/mcp" -ForegroundColor Green
Write-Host "Runtime key storage: Windows DPAPI current-user store" -ForegroundColor Green
Write-Host "OpenAI/ChatGPT workspace visibility still depends on the tunnel being associated with the intended workspace." -ForegroundColor Yellow
exit 0
