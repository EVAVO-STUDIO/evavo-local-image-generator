# Connect the EVAVO private MCP endpoint to ChatGPT through OpenAI Secure MCP Tunnel.
# CONTROL_PLANE_API_KEY is read from the current environment or decrypted from
# the current Windows user's DPAPI store. It is never written in plaintext.

param(
    [string]$Profile,
    [int]$McpPort = 0,
    [switch]$SkipDoctor,
    [switch]$SkipLocalMcpStart
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$statePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
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
    throw "Tunnel profile is missing or invalid. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}

# Unless explicitly overridden, start/check the exact private MCP port stored in
# the tunnel profile. This keeps custom-port installs correct across reboot.
if ($McpPort -eq 0) {
    $savedMcpUrl = [string]$state.mcp_server_url
    try {
        $savedMcpUri = [uri]$savedMcpUrl
    }
    catch {
        throw "Saved tunnel MCP URL is invalid. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
    }
    if ($savedMcpUri.Scheme -ne "http" -or $savedMcpUri.Host -notin @("127.0.0.1", "localhost", "::1")) {
        throw "Saved tunnel MCP URL is not a private loopback HTTP endpoint. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
    }
    $McpPort = [int]$savedMcpUri.Port
}
if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    throw "MCP port must be between 1 and 65535."
}

$binary = [string]$state.tunnel_client
if (-not $binary -or -not (Test-Path $binary)) {
    $binary = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client.exe"
}
if (-not (Test-Path $binary)) {
    throw "OpenAI tunnel-client is not installed. Run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}

# The installed executable must still match the digest recorded immediately
# after extraction from the verified official release archive. This check runs
# on every manual/login tunnel start, not only during installation.
$metadataPath = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client-install.json"
if (-not (Test-Path $metadataPath)) {
    throw "Tunnel-client integrity metadata is missing. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}
try {
    $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
    $expectedBinaryHash = [string]$metadata.binary_digest
}
catch {
    throw "Tunnel-client integrity metadata is invalid. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}
if ($expectedBinaryHash -notmatch '^[0-9a-f]{64}$') {
    throw "Tunnel-client integrity metadata does not contain a valid executable SHA-256. Re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}
$actualBinaryHash = (Get-FileHash -Path $binary -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualBinaryHash -ne $expectedBinaryHash) {
    throw "Tunnel-client executable SHA-256 does not match the verified-install record. Refusing to run; re-run INSTALL-CHATGPT-MCP-TUNNEL.ps1."
}

# Load the runtime key. A caller-supplied environment key is preserved. Only a
# key temporarily decrypted by this script is cleared on exit.
$loadedFromDpapi = $false
if (-not $env:CONTROL_PLANE_API_KEY) {
    if (-not $env:LOCALAPPDATA) {
        throw "CONTROL_PLANE_API_KEY is not set and LOCALAPPDATA is unavailable for DPAPI key storage."
    }
    $keyPath = Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi"
    if (-not (Test-Path $keyPath)) {
        throw "CONTROL_PLANE_API_KEY is not set and no DPAPI tunnel key is stored. Run SAVE-CHATGPT-TUNNEL-KEY.ps1 once."
    }
    try {
        $secure = Get-Content $keyPath -Raw | ConvertTo-SecureString
        $credential = New-Object System.Management.Automation.PSCredential("evavo-tunnel", $secure)
        $env:CONTROL_PLANE_API_KEY = $credential.GetNetworkCredential().Password
        $loadedFromDpapi = [bool]$env:CONTROL_PLANE_API_KEY
    }
    catch {
        throw "The stored tunnel key could not be decrypted for this Windows user. Re-run SAVE-CHATGPT-TUNNEL-KEY.ps1."
    }
    if (-not $env:CONTROL_PLANE_API_KEY) {
        throw "The stored tunnel key decrypted to an empty value."
    }
}

function Get-ListenerOwner([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Pid = [int]$listener.OwningProcess
        CommandLine = if ($owner) { [string]$owner.CommandLine } else { "" }
    }
}

try {
    if (-not $SkipLocalMcpStart) {
        $owner = Get-ListenerOwner $McpPort
        if ($owner -and $owner.CommandLine -notmatch "evavo_local_image_generator\.mcp_server") {
            throw "Port $McpPort is already owned by PID $($owner.Pid), which is not EVAVO MCP."
        }
        if (-not $owner) {
            $starter = Join-Path $PSScriptRoot "START-AGENT-MCP.ps1"
            $quotedStarter = '"' + $starter.Replace('"', '\"') + '"'
            $args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $quotedStarter -Port $McpPort -SkipValidation"
            Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null

            $deadline = (Get-Date).AddSeconds(30)
            do {
                Start-Sleep -Milliseconds 300
                $owner = Get-ListenerOwner $McpPort
            } while (-not $owner -and (Get-Date) -lt $deadline)
            if (-not $owner) {
                throw "EVAVO MCP did not start on port $McpPort within 30 seconds."
            }
            if ($owner.CommandLine -notmatch "evavo_local_image_generator\.mcp_server") {
                throw "Port $McpPort became occupied by PID $($owner.Pid), which is not EVAVO MCP."
            }
        }
    }

    if (-not $SkipDoctor) {
        Write-Host "Running OpenAI tunnel-client doctor for '$Profile'..." -ForegroundColor Cyan
        & $binary doctor --profile $Profile --explain
        if ($LASTEXITCODE -ne 0) {
            throw "OpenAI tunnel-client doctor reported a blocking problem."
        }
    }

    Write-Host "Connecting EVAVO to OpenAI Secure MCP Tunnel using profile '$Profile'..." -ForegroundColor Green
    Write-Host "The tunnel is outbound-only; the EVAVO MCP server remains private on localhost:$McpPort." -ForegroundColor Green
    & $binary run --profile $Profile
    $code = $LASTEXITCODE
}
finally {
    if ($loadedFromDpapi) {
        $env:CONTROL_PLANE_API_KEY = $null
        $credential = $null
    }
}
exit $code
