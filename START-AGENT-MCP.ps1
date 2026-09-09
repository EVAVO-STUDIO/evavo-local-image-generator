# Start EVAVO MCP over loopback Streamable HTTP for ChatGPT/local MCP clients.
param(
    [int]$Port = 8765,
    [string]$Path = "/mcp",
    [switch]$JsonResponse,
    [switch]$SkipValidation,
    [switch]$RestartIfRunning
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
$python = (Resolve-Path $python).Path

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535."
}
if (-not $Path.StartsWith("/")) {
    throw "Path must start with '/'."
}

$env:EVAVO_AUTO_PROVISION_COMFYUI = "1"
$env:EVAVO_AUTO_PROVISION_CHECKPOINT = "1"

function Test-EvavoMcpListenerIdentity($Listener) {
    if (-not $Listener) { return $false }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $owner) { return $false }

    $commandLine = [string]$owner.CommandLine
    $executable = [string]$owner.ExecutablePath
    $escapedPath = [regex]::Escape($Path)
    $requiredArgs = @(
        "evavo_local_image_generator\.mcp_server",
        "--transport\s+streamable-http",
        "--host\s+127\.0\.0\.1",
        "--port\s+$Port(?:\s|$)",
        "--path\s+(?:`"$escapedPath`"|$escapedPath)(?:\s|$)"
    )
    foreach ($pattern in $requiredArgs) {
        if ($commandLine -notmatch $pattern) { return $false }
    }

    # Strong identity path 1: the listener is using the Python runtime this
    # checkout would use now.
    if ($executable -and [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($executable), [IO.Path]::GetFullPath($python))) {
        return $true
    }

    # Strong identity path 2: migration from an older/system Python is allowed
    # only when the listener's parent is this exact repository launcher.
    $parentPid = [int]$owner.ParentProcessId
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

function Wait-PortClosed([int]$PortNumber, [int]$Seconds = 10) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $stillListening = Get-NetTCPConnection -LocalPort $PortNumber -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $stillListening) { return $true }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    return $false
}

# Avoid duplicate login/manual listeners. A verified listener can be recycled
# after an update so the process actually loads the current checkout. Unknown
# processes are never adopted or stopped.
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    if (-not (Test-EvavoMcpListenerIdentity $listener)) {
        throw "Port $Port is already owned by PID $($listener.OwningProcess), but EVAVO cannot prove it is this repository's MCP listener. Refusing to adopt or stop it."
    }
    if (-not $RestartIfRunning) {
        Write-Host "Verified EVAVO MCP is already listening at http://127.0.0.1:$Port$Path (PID $($listener.OwningProcess))." -ForegroundColor Green
        exit 0
    }

    Write-Host "Restarting verified EVAVO MCP listener PID $($listener.OwningProcess) so it loads the current checkout..." -ForegroundColor Cyan
    Stop-Process -Id ([int]$listener.OwningProcess) -Force -ErrorAction Stop
    if (-not (Wait-PortClosed $Port 10)) {
        throw "Verified EVAVO MCP listener was signalled but port $Port is still in use."
    }
}

if (-not $SkipValidation) {
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
