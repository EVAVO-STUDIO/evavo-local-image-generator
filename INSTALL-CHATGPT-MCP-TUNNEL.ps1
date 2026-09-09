# Install/update OpenAI tunnel-client and configure an EVAVO ChatGPT tunnel profile.
# The runtime API key is never written by this script unless -PersistRuntimeKey
# is explicitly requested, in which case SAVE-CHATGPT-TUNNEL-KEY.ps1 stores it
# with Windows DPAPI for the current user.

param(
    [string]$TunnelId = $env:EVAVO_OPENAI_TUNNEL_ID,
    [string]$Profile = "evavo-chatgpt",
    [int]$McpPort = 8765,
    [switch]$PersistRuntimeKey,
    [switch]$SkipLocalMcpInstall,
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail([string]$Message) {
    throw $Message
}

if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    Fail "MCP port must be between 1 and 65535."
}
if (-not $Profile -or $Profile -notmatch '^[A-Za-z0-9._-]+$') {
    Fail "Tunnel profile must contain only letters, digits, '.', '_' or '-'."
}

$stateDir = Join-Path $PSScriptRoot ".evavo"
$toolsDir = Join-Path $stateDir "tools"
$statePath = Join-Path $stateDir "chatgpt-tunnel.json"
$binary = Join-Path $toolsDir "tunnel-client.exe"
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

if (-not $TunnelId -and (Test-Path $statePath)) {
    try {
        $existingState = Get-Content $statePath -Raw | ConvertFrom-Json
        if ($existingState.tunnel_id) {
            $TunnelId = [string]$existingState.tunnel_id
        }
    }
    catch {
        Write-Host "Existing tunnel state is unreadable and will be replaced after a valid TunnelId is supplied." -ForegroundColor Yellow
    }
}

if (-not $TunnelId) {
    Fail "No OpenAI tunnel ID is configured. Create/associate a Secure MCP Tunnel in OpenAI Platform, then set EVAVO_OPENAI_TUNNEL_ID or pass -TunnelId tunnel_<32 lowercase hex characters>."
}
if ($TunnelId -notmatch '^tunnel_[0-9a-f]{32}$') {
    Fail "TunnelId must match OpenAI's tunnel_<32 lowercase hexadecimal characters> format: $TunnelId"
}

# Download the latest official public release and verify the SHA-256 digest
# advertised by GitHub's release asset metadata before extracting it.
Write-Host "Resolving latest official OpenAI tunnel-client release..." -ForegroundColor Cyan
$headers = @{ "User-Agent" = "EVAVO-Tunnel-Installer/1"; "Accept" = "application/vnd.github+json" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/openai/tunnel-client/releases/latest" -Headers $headers

$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$archToken = switch ($architecture) {
    "X64" { "amd64" }
    "Arm64" { "arm64" }
    default { Fail "Unsupported Windows architecture for tunnel-client: $architecture" }
}
$assetPattern = "^tunnel-client-v.*-windows-$archToken\.zip$"
$asset = $release.assets | Where-Object { $_.name -match $assetPattern } | Select-Object -First 1
if (-not $asset) {
    Fail "Latest OpenAI tunnel-client release does not contain a Windows $archToken package."
}
if (-not $asset.digest -or [string]$asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
    Fail "Release asset does not publish a usable SHA-256 digest; refusing unverified install."
}
$expectedHash = $Matches[1].ToLowerInvariant()

$needsInstall = $true
$metadataPath = Join-Path $toolsDir "tunnel-client-install.json"
if ((Test-Path $binary) -and (Test-Path $metadataPath)) {
    try {
        $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
        if ([string]$metadata.release_tag -eq [string]$release.tag_name -and [string]$metadata.asset_digest -eq $expectedHash) {
            & $binary help quickstart *> $null
            if ($LASTEXITCODE -eq 0) {
                $needsInstall = $false
                Write-Host "OpenAI tunnel-client $($release.tag_name) is already installed and executable." -ForegroundColor Green
            }
        }
    }
    catch {
        $needsInstall = $true
    }
}

if ($needsInstall) {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("evavo-tunnel-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    $zip = Join-Path $tempRoot $asset.name
    $extract = Join-Path $tempRoot "extract"
    try {
        Write-Host "Downloading $($asset.name)..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $zip
        $actualHash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            Fail "OpenAI tunnel-client SHA-256 mismatch. Expected $expectedHash, got $actualHash."
        }
        Expand-Archive -Path $zip -DestinationPath $extract -Force
        $candidate = Get-ChildItem -Path $extract -Recurse -File -Filter "tunnel-client*.exe" |
            Where-Object { $_.Name -notmatch 'runtime' } |
            Select-Object -First 1
        if (-not $candidate) {
            Fail "Verified tunnel-client archive did not contain a tunnel-client executable."
        }
        Copy-Item -Path $candidate.FullName -Destination $binary -Force
        & $binary help quickstart *> $null
        if ($LASTEXITCODE -ne 0) {
            Fail "Installed tunnel-client executable failed its help smoke check."
        }
        $installMetadata = [ordered]@{
            repository = "openai/tunnel-client"
            release_tag = [string]$release.tag_name
            asset_name = [string]$asset.name
            asset_digest = $expectedHash
            installed_at = (Get-Date).ToString("o")
            binary = $binary
        }
        $installMetadata | ConvertTo-Json -Depth 6 | Set-Content -Path $metadataPath -Encoding UTF8
        Write-Host "Installed verified OpenAI tunnel-client $($release.tag_name)." -ForegroundColor Green
    }
    finally {
        Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipLocalMcpInstall) {
    Write-Host "Ensuring the EVAVO private MCP endpoint is configured and running..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-AGENT-MCP-AUTOSTART.ps1") -Port $McpPort -SkipValidation
    if ($LASTEXITCODE -ne 0) {
        Fail "EVAVO local MCP setup failed."
    }
}

$mcpUrl = "http://127.0.0.1:$McpPort/mcp"
Write-Host "Materializing OpenAI tunnel profile '$Profile'..." -ForegroundColor Cyan
& $binary init `
    --sample sample_mcp_with_dcr `
    --profile $Profile `
    --force `
    --tunnel-id $TunnelId `
    --mcp-server-url $mcpUrl
if ($LASTEXITCODE -ne 0) {
    Fail "tunnel-client profile initialization failed."
}

$state = [ordered]@{
    tunnel_id = $TunnelId
    profile = $Profile
    mcp_server_url = $mcpUrl
    tunnel_client = $binary
    release_tag = [string]$release.tag_name
    configured_at = (Get-Date).ToString("o")
}
$state | ConvertTo-Json -Depth 6 | Set-Content -Path $statePath -Encoding UTF8

if ($PersistRuntimeKey) {
    & (Join-Path $PSScriptRoot "SAVE-CHATGPT-TUNNEL-KEY.ps1") -FromEnvironment
    if ($LASTEXITCODE -ne 0) {
        Fail "Unable to persist the tunnel runtime key securely."
    }
}

if (-not $SkipDoctor) {
    $keyAvailable = [bool]$env:CONTROL_PLANE_API_KEY
    $loadedFromDpapi = $false
    $secureKeyPath = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi" } else { $null }
    if (-not $keyAvailable -and $secureKeyPath -and (Test-Path $secureKeyPath)) {
        try {
            $secure = Get-Content $secureKeyPath -Raw | ConvertTo-SecureString
            $credential = New-Object System.Management.Automation.PSCredential("evavo-tunnel", $secure)
            $env:CONTROL_PLANE_API_KEY = $credential.GetNetworkCredential().Password
            $keyAvailable = [bool]$env:CONTROL_PLANE_API_KEY
            $loadedFromDpapi = $keyAvailable
        }
        catch {
            Write-Host "Stored tunnel key could not be decrypted in this Windows user context." -ForegroundColor Yellow
        }
    }
    try {
        if ($keyAvailable) {
            Write-Host "Running tunnel-client local preflight doctor..." -ForegroundColor Cyan
            & $binary doctor --profile $Profile --explain
            if ($LASTEXITCODE -ne 0) {
                Fail "OpenAI tunnel-client local preflight doctor reported a blocking problem."
            }
            Write-Host "Local tunnel preflight passed. Runtime authorization/workspace visibility is validated by the running tunnel and ChatGPT connector setup, not by doctor alone." -ForegroundColor DarkGray
        }
        else {
            Write-Host "Tunnel profile installed, but CONTROL_PLANE_API_KEY is not available, so tunnel-client doctor was skipped." -ForegroundColor Yellow
            Write-Host "Set the runtime key for this shell or run SAVE-CHATGPT-TUNNEL-KEY.ps1 once for encrypted Windows-user storage." -ForegroundColor Yellow
        }
    }
    finally {
        if ($loadedFromDpapi) {
            $env:CONTROL_PLANE_API_KEY = $null
            $credential = $null
        }
    }
}

Write-Host ""
Write-Host "EVAVO ChatGPT Secure MCP Tunnel profile is configured." -ForegroundColor Green
Write-Host "  Tunnel ID: $TunnelId" -ForegroundColor Green
Write-Host "  Profile:   $Profile" -ForegroundColor Green
Write-Host "  Private MCP target: $mcpUrl" -ForegroundColor Green
Write-Host "  Binary:    $binary" -ForegroundColor Green
Write-Host "Run START-CHATGPT-MCP-TUNNEL.ps1 to start the outbound tunnel runtime." -ForegroundColor Green
