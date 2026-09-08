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

Write-Host "Validating EVAVO agent integration..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-agent-integration.py")
if ($LASTEXITCODE -ne 0) {
    throw "Agent integration tests failed."
}

Write-Host "Ensuring native ComfyUI can be discovered/started when required..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") doctor

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
Write-Host "Native ComfyUI will auto-start on the first tool call when EVAVO can locate it." -ForegroundColor Green
& $python @argsList
exit $LASTEXITCODE
