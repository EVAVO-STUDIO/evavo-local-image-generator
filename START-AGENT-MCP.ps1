# Start EVAVO MCP over loopback Streamable HTTP for ChatGPT/local MCP clients.
param(
    [int]$Port = 8765,
    [string]$Path = "/mcp",
    [switch]$JsonResponse
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Python 3.10+ was not found."
    }
    $python = $cmd.Source
}

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535."
}
if (-not $Path.StartsWith("/")) {
    throw "Path must start with '/'."
}

# HTTP MCP may provision the fixed official ComfyUI runtime and may install an
# owner-configured checkpoint when the built-in workflow needs one. No arbitrary
# checkpoint URL is accepted through an MCP tool argument.
$env:EVAVO_AUTO_PROVISION_COMFYUI = "1"
$env:EVAVO_AUTO_PROVISION_CHECKPOINT = "1"

# Avoid duplicate login/manual listeners and never take over an unrelated port.
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = if ($owner) { [string]$owner.CommandLine } else { "" }
    if ($commandLine -match "evavo_local_image_generator\.mcp_server") {
        Write-Host "EVAVO MCP is already listening at http://127.0.0.1:$Port$Path (PID $($listener.OwningProcess))." -ForegroundColor Green
        exit 0
    }
    throw "Port $Port is already owned by PID $($listener.OwningProcess), which is not the EVAVO MCP server. Choose another -Port or stop that process."
}

Write-Host "Validating EVAVO agent integration..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-agent-integration.py")
if ($LASTEXITCODE -ne 0) {
    throw "Agent integration tests failed."
}

Write-Host "Checking EVAVO/ComfyUI environment..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") doctor
if ($LASTEXITCODE -ne 0) {
    throw "EVAVO operations doctor found a blocking problem."
}

$argsList = @(
    "-m", "evavo_local_image_generator.mcp_server",
    "--transport", "streamable-http",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--path", $Path
)
if ($JsonResponse) {
    $argsList += "--json-response"
}

Write-Host "Starting EVAVO MCP at http://127.0.0.1:$Port$Path" -ForegroundColor Green
Write-Host "Native ComfyUI will auto-start/provision; configured checkpoints can auto-repair the built-in workflow." -ForegroundColor Green
& $python @argsList
exit $LASTEXITCODE
