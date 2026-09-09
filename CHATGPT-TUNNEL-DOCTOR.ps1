# Diagnose the EVAVO ChatGPT Secure MCP Tunnel without exposing secrets.

param(
    [string]$Profile,
    [switch]$RequireRuntimeKey,
    [switch]$RequireRunning,
    [switch]$SkipControlPlane,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$checks = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$Name, [bool]$Ok, [string]$Detail, [string]$Severity = "error") {
    $checks.Add([pscustomobject][ordered]@{
        name = $Name
        ok = $Ok
        severity = $Severity
        detail = $Detail
    })
}

$statePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
$state = $null
if (Test-Path $statePath) {
    try {
        $state = Get-Content $statePath -Raw | ConvertFrom-Json
        Add-Check "tunnel_state" $true "configured: $statePath"
    }
    catch {
        Add-Check "tunnel_state" $false "invalid JSON: $statePath"
    }
}
else {
    Add-Check "tunnel_state" $false "not configured; run INSTALL-CHATGPT-MCP-TUNNEL.ps1"
}

if (-not $Profile -and $state) {
    $Profile = [string]$state.profile
}
$profileOk = [bool]$Profile -and $Profile -match '^[A-Za-z0-9._-]+$'
Add-Check "profile" $profileOk ($(if ($profileOk) { $Profile } else { "missing or invalid" }))

$tunnelId = if ($state) { [string]$state.tunnel_id } else { "" }
$tunnelIdOk = [bool]$tunnelId -and $tunnelId -match '^tunnel_[A-Za-z0-9_-]{8,}$'
Add-Check "tunnel_id" $tunnelIdOk ($(if ($tunnelIdOk) { $tunnelId } else { "missing or invalid" }))

$mcpUrl = if ($state -and $state.mcp_server_url) { [string]$state.mcp_server_url } else { "http://127.0.0.1:8765/mcp" }
$uri = $null
try {
    $uri = [uri]$mcpUrl
}
catch {
}
$localUrlOk = $null -ne $uri -and $uri.Scheme -eq "http" -and $uri.Host -in @("127.0.0.1", "localhost", "::1") -and $uri.AbsolutePath.StartsWith("/")
Add-Check "private_mcp_url" $localUrlOk ($(if ($localUrlOk) { $mcpUrl } else { "invalid private MCP URL in tunnel state" }))

$binary = if ($state -and $state.tunnel_client) { [string]$state.tunnel_client } else { "" }
if (-not $binary -or -not (Test-Path $binary)) {
    $binary = Join-Path $PSScriptRoot ".evavo\tools\tunnel-client.exe"
}
$binaryOk = Test-Path $binary
if ($binaryOk) {
    try {
        & $binary help quickstart *> $null
        $binaryOk = $LASTEXITCODE -eq 0
    }
    catch {
        $binaryOk = $false
    }
}
Add-Check "tunnel_client" $binaryOk ($(if ($binaryOk) { $binary } else { "missing or not executable; run INSTALL-CHATGPT-MCP-TUNNEL.ps1" }))

$localMcpOk = $false
$localMcpDetail = "not checked"
if ($localUrlOk -and $uri) {
    $port = if ($uri.Port -gt 0) { $uri.Port } else { 80 }
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $commandLine = if ($owner) { [string]$owner.CommandLine } else { "" }
        if ($commandLine -match "evavo_local_image_generator\.mcp_server") {
            $localMcpOk = $true
            $localMcpDetail = "EVAVO MCP listening on $($uri.Host):$port (PID $($listener.OwningProcess))"
        }
        else {
            $localMcpDetail = "port $port is owned by PID $($listener.OwningProcess), not EVAVO MCP"
        }
    }
    else {
        $localMcpDetail = "no listener on $($uri.Host):$port"
    }
}
Add-Check "local_mcp" $localMcpOk $localMcpDetail "warning"

$keySource = "none"
$keyAvailable = [bool]$env:CONTROL_PLANE_API_KEY
if ($keyAvailable) {
    $keySource = "process environment"
}
elseif ($env:LOCALAPPDATA) {
    $keyPath = Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi"
    if (Test-Path $keyPath) {
        try {
            $secure = Get-Content $keyPath -Raw | ConvertTo-SecureString
            $credential = New-Object System.Management.Automation.PSCredential("evavo-tunnel", $secure)
            $decrypted = $credential.GetNetworkCredential().Password
            if ($decrypted) {
                $env:CONTROL_PLANE_API_KEY = $decrypted
                $keyAvailable = $true
                $keySource = "Windows DPAPI current-user store"
            }
        }
        catch {
            $keySource = "DPAPI blob exists but could not be decrypted in this user context"
        }
    }
}
$keySeverity = if ($RequireRuntimeKey) { "error" } else { "warning" }
Add-Check "runtime_key" $keyAvailable ($(if ($keyAvailable) { "available from $keySource" } else { $keySource })) $keySeverity

$controlPlaneOk = $false
$controlPlaneDetail = "skipped"
if (-not $SkipControlPlane -and $binaryOk -and $profileOk -and $keyAvailable) {
    try {
        $doctorOutput = & $binary doctor --profile $Profile --explain 2>&1
        $controlPlaneOk = $LASTEXITCODE -eq 0
        if ($controlPlaneOk) {
            $controlPlaneDetail = "tunnel-client doctor passed"
        }
        else {
            $controlPlaneDetail = (($doctorOutput | Out-String).Trim())
            if ($controlPlaneDetail.Length -gt 1200) {
                $controlPlaneDetail = $controlPlaneDetail.Substring($controlPlaneDetail.Length - 1200)
            }
        }
    }
    catch {
        $controlPlaneDetail = $_.Exception.Message
    }
}
elseif ($SkipControlPlane) {
    $controlPlaneOk = $true
    $controlPlaneDetail = "skipped by request"
}
elseif (-not $keyAvailable) {
    $controlPlaneDetail = "runtime key unavailable"
}
else {
    $controlPlaneDetail = "binary/profile unavailable"
}
$controlPlaneSeverity = if ($RequireRuntimeKey -and -not $SkipControlPlane) { "error" } else { "warning" }
Add-Check "control_plane_doctor" $controlPlaneOk $controlPlaneDetail $controlPlaneSeverity

$process = $null
if ($profileOk) {
    $escaped = [regex]::Escape($Profile)
    $process = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            ([string]$_.Name -ieq "tunnel-client.exe") -and
            ([string]$_.CommandLine -match "\brun\b") -and
            ([string]$_.CommandLine -match "--profile\s+(`"|')?$escaped(`"|')?(\s|$)")
        } |
        Select-Object -First 1
}
$running = $null -ne $process
$runningSeverity = if ($RequireRunning) { "error" } else { "warning" }
Add-Check "tunnel_process" $running ($(if ($running) { "running PID $($process.ProcessId)" } else { "not running" })) $runningSeverity

$hardFailures = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "error" })
$warnings = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "warning" })
$status = if ($hardFailures.Count -gt 0) { "needs_attention" } elseif ($running -and $controlPlaneOk -and $localMcpOk) { "running" } elseif ($warnings.Count -gt 0) { "configured_with_warnings" } else { "ready_to_start" }
$payload = [pscustomobject][ordered]@{
    ok = $hardFailures.Count -eq 0
    status = $status
    profile = $Profile
    tunnel_id = $tunnelId
    private_mcp_url = $mcpUrl
    checks = @($checks)
}

# Never leave a DPAPI-decrypted key in the current PowerShell process after the doctor.
if ($keySource -eq "Windows DPAPI current-user store") {
    $env:CONTROL_PLANE_API_KEY = $null
    $decrypted = $null
    $credential = $null
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 10
}
else {
    Write-Host "EVAVO ChatGPT Tunnel Doctor" -ForegroundColor Cyan
    Write-Host ("=" * 82)
    foreach ($check in $checks) {
        $marker = if ($check.ok) { "OK" } elseif ($check.severity -eq "warning") { "WARN" } else { "FAIL" }
        Write-Host ("[{0,-4}] {1,-24} {2}" -f $marker, $check.name, $check.detail)
    }
    Write-Host ("=" * 82)
    Write-Host $status
}

if ($hardFailures.Count -gt 0) {
    exit 2
}
exit 0
