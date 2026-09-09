# Stop only the EVAVO-owned/local MCP listener on the requested loopback port.
# No broad Python termination is performed.

param(
    [int]$Port = 8765,
    [string]$Path = "/mcp",
    [switch]$RemoveAutostart
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "MCP port must be between 1 and 65535."
}
if (-not $Path.StartsWith("/")) {
    throw "MCP path must start with '/'."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Python 3.10+ was not found, so EVAVO cannot verify the MCP listener runtime identity."
    }
    $python = $cmd.Source
}
$python = (Resolve-Path $python).Path

function Test-EvavoMcpListenerIdentity($Listener) {
    if (-not $Listener) { return $false }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $process) { return $false }

    $commandLine = [string]$process.CommandLine
    $executable = [string]$process.ExecutablePath
    $escapedPath = [regex]::Escape($Path)
    $requiredArgs = @(
        "evavo_local_image_generator\.(?:mcp_entry|mcp_server)",
        "--transport\s+streamable-http",
        "--host\s+127\.0\.0\.1",
        "--port\s+$Port(?:\s|$)",
        "--path\s+(?:`"$escapedPath`"|$escapedPath)(?:\s|$)"
    )
    foreach ($pattern in $requiredArgs) {
        if ($commandLine -notmatch $pattern) { return $false }
    }

    $isValidatedEntry = $commandLine -match "evavo_local_image_generator\.mcp_entry"
    if ($isValidatedEntry -and $executable -and [System.StringComparer]::OrdinalIgnoreCase.Equals([System.IO.Path]::GetFullPath($executable), [System.IO.Path]::GetFullPath($python))) {
        return $true
    }

    # Legacy mcp_server migration/shutdown is allowed only when the parent is
    # this exact repository launcher. Unknown manually-created Python listeners
    # are not adopted merely because they import a similarly named module.
    $parentPid = [int]$process.ParentProcessId
    if ($parentPid -gt 0) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentPid" -ErrorAction SilentlyContinue
        $parentCommand = if ($parent) { [string]$parent.CommandLine } else { "" }
        $escapedLauncher = [regex]::Escape((Join-Path $PSScriptRoot "START-AGENT-MCP.ps1"))
        if ($parentCommand -match $escapedLauncher) {
            return $true
        }
    }
    return $false
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $listener) {
    Write-Host "No process is listening on MCP port $Port." -ForegroundColor Green
}
else {
    $pidValue = [int]$listener.OwningProcess
    if (-not (Test-EvavoMcpListenerIdentity $listener)) {
        throw "Port $Port is owned by PID $pidValue, but EVAVO cannot prove it is this repository's Streamable HTTP MCP listener. Refusing to stop it."
    }

    Stop-Process -Id $pidValue -Force -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } while ($stillListening -and (Get-Date) -lt $deadline)
    if ($stillListening) {
        throw "Verified EVAVO MCP PID $pidValue was signalled but port $Port is still listening."
    }
    Write-Host "Stopped verified EVAVO private MCP listener PID $pidValue on port $Port." -ForegroundColor Green
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
