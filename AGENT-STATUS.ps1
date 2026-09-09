# Unified read-only status for EVAVO native image generation and agent access.

param(
    [int]$McpPort = 8765,
    [switch]$Json,
    [switch]$CheckTunnelControlPlane
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    throw "MCP port must be between 1 and 65535."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { throw "Python 3.10+ was not found." }
    $python = $command.Source
}

function Invoke-JsonPython([string[]]$Arguments) {
    $raw = & $python @Arguments 2>&1
    $code = $LASTEXITCODE
    $text = ($raw | Out-String).Trim()
    try {
        $payload = if ($text) { $text | ConvertFrom-Json } else { $null }
    }
    catch {
        $payload = $null
    }
    return [pscustomobject]@{ exit_code = $code; payload = $payload; raw = $text }
}

$repoDoctor = Invoke-JsonPython @((Join-Path $PSScriptRoot "evavo.py"), "doctor", "--json")
$agentDoctor = Invoke-JsonPython @((Join-Path $PSScriptRoot "agent-doctor.py"), "--json", "--skip-tests", "--mcp-port", "$McpPort")
$backendStatus = Invoke-JsonPython @((Join-Path $PSScriptRoot "evavo.py"), "status")

$mcpListener = Get-NetTCPConnection -LocalPort $McpPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$mcp = [ordered]@{
    ready = $false
    port = $McpPort
    pid = $null
    identity = "not_running"
}
if ($mcpListener) {
    $pidValue = [int]$mcpListener.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
    $commandLine = if ($process) { [string]$process.CommandLine } else { "" }
    $mcp.pid = $pidValue
    if ($commandLine -match "evavo_local_image_generator\.mcp_server" -and $commandLine -match "--transport\s+streamable-http") {
        $mcp.ready = $true
        $mcp.identity = "evavo_streamable_http"
    }
    else {
        $mcp.identity = "unexpected_listener"
    }
}

$tunnelState = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
$tunnel = [ordered]@{
    configured = Test-Path $tunnelState
    status = "not_configured"
    payload = $null
    exit_code = $null
}
if ($tunnel.configured) {
    $doctor = Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1"
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $doctor, "-Json")
    if (-not $CheckTunnelControlPlane) {
        $args += "-SkipControlPlane"
    }
    $raw = & powershell.exe @args 2>&1
    $code = $LASTEXITCODE
    $text = ($raw | Out-String).Trim()
    try { $payload = if ($text) { $text | ConvertFrom-Json } else { $null } } catch { $payload = $null }
    $tunnel.exit_code = $code
    $tunnel.payload = $payload
    if ($payload -and $payload.status) {
        $tunnel.status = [string]$payload.status
    }
    elseif ($code -eq 0) {
        $tunnel.status = "configured"
    }
    else {
        $tunnel.status = "needs_attention"
    }
}

$repoOk = $repoDoctor.exit_code -eq 0 -and $repoDoctor.payload -and $repoDoctor.payload.ok
$agentOk = $agentDoctor.exit_code -eq 0 -and $agentDoctor.payload -and $agentDoctor.payload.ok
$backendOk = $backendStatus.exit_code -eq 0 -and $backendStatus.payload -and $backendStatus.payload.ok
$localReady = [bool]($repoOk -and $agentOk -and $backendOk)

$payload = [pscustomobject][ordered]@{
    ok = $localReady
    status = if ($localReady) { "local_image_runtime_ready" } else { "needs_attention" }
    repository = [ordered]@{ ok = [bool]$repoOk; exit_code = $repoDoctor.exit_code; payload = $repoDoctor.payload; raw = if ($repoDoctor.payload) { $null } else { $repoDoctor.raw } }
    agent = [ordered]@{ ok = [bool]$agentOk; exit_code = $agentDoctor.exit_code; payload = $agentDoctor.payload; raw = if ($agentDoctor.payload) { $null } else { $agentDoctor.raw } }
    backend = [ordered]@{ ok = [bool]$backendOk; exit_code = $backendStatus.exit_code; payload = $backendStatus.payload; raw = if ($backendStatus.payload) { $null } else { $backendStatus.raw } }
    private_mcp = $mcp
    chatgpt_tunnel = $tunnel
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 16
}
else {
    Write-Host "EVAVO Agent Status" -ForegroundColor Cyan
    Write-Host ("=" * 84)
    Write-Host ("Repository/operations: {0}" -f $(if ($repoOk) { "OK" } else { "NEEDS ATTENTION" }))
    Write-Host ("Native image readiness: {0}" -f $(if ($agentOk -and $backendOk) { "OK" } else { "NEEDS ATTENTION" }))
    Write-Host ("Private HTTP MCP: {0} ({1})" -f $(if ($mcp.ready) { "RUNNING" } else { "NOT READY" }), $mcp.identity)
    Write-Host ("ChatGPT tunnel: {0}" -f $tunnel.status)
    Write-Host ("=" * 84)
    Write-Host $payload.status
    if (-not $tunnel.configured) {
        Write-Host "ChatGPT tunnel is optional for local/Claude use; configure it when cloud ChatGPT workstation access is needed." -ForegroundColor Yellow
    }
}

exit $(if ($localReady) { 0 } else { 2 })
