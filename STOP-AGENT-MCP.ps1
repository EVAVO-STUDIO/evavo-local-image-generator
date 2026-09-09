# Stop only the EVAVO-owned/local MCP listener on the requested loopback port.
# No broad Python termination is performed.

param(
    [int]$Port = 8765,
    [switch]$RemoveAutostart
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "MCP port must be between 1 and 65535."
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $listener) {
    Write-Host "No process is listening on MCP port $Port." -ForegroundColor Green
}
else {
    $pidValue = [int]$listener.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
    $commandLine = if ($process) { [string]$process.CommandLine } else { "" }
    if (-not $process -or $commandLine -notmatch "evavo_local_image_generator\.mcp_server") {
        throw "Port $Port is owned by PID $pidValue, but its command line is not the EVAVO MCP server. Refusing to stop it."
    }
    if ($commandLine -notmatch "--transport\s+streamable-http") {
        throw "PID $pidValue is an EVAVO MCP process but is not the Streamable HTTP listener. Refusing to stop it through this command."
    }
    Stop-Process -Id $pidValue -Force -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } while ($stillListening -and (Get-Date) -lt $deadline)
    if ($stillListening) {
        throw "EVAVO MCP PID $pidValue was signalled but port $Port is still listening."
    }
    Write-Host "Stopped EVAVO private MCP listener PID $pidValue on port $Port." -ForegroundColor Green
}

if ($RemoveAutostart) {
    $installer = Join-Path $PSScriptRoot "INSTALL-AGENT-MCP-AUTOSTART.ps1"
    if (-not (Test-Path $installer)) {
        throw "Autostart installer is missing: $installer"
    }
    & $installer -Uninstall -Port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove private MCP login autostart."
    }
}

exit 0
