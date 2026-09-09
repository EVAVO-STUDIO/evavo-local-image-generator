# EVAVO Local Image Generator - update, install, validate, configure agents and verify
# Safe by default: refuses to overwrite local Git changes, only fast-forwards
# verified origin/main, and keeps EVAVO Python dependencies inside .venv.

param(
    [switch]$SkipDependencies,
    [switch]$SkipAgentConfiguration,
    [switch]$SkipComfyUIProvision,
    [switch]$SkipComfyUIDependencyRepair,
    [switch]$SkipChatGPTTunnel,
    [int]$McpPort = 8765
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Fail([string]$Message, [int]$Code = 1) {
    Write-Error $Message
    exit $Code
}

function Test-Truthy([string]$Value) {
    if (-not $Value) { return $false }
    return $Value.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
}

if ($McpPort -lt 1 -or $McpPort -gt 65535) {
    Fail "MCP port must be between 1 and 65535." 2
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git is not installed or not available on PATH." 2
}

$origin = (git remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or -not $origin) {
    Fail "Unable to resolve the repository origin remote." 2
}
$expectedOrigin = '^(?:https://github\.com/EVAVO-STUDIO/evavo-local-image-generator(?:\.git)?|git@github\.com:EVAVO-STUDIO/evavo-local-image-generator(?:\.git)?|ssh://git@github\.com/EVAVO-STUDIO/evavo-local-image-generator(?:\.git)?)$'
if ($origin -notmatch $expectedOrigin) {
    Fail "Refusing to update from unexpected origin: $origin" 2
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    Fail "Repository must be on branch main. Current branch: $branch" 2
}
$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0) { Fail "Unable to inspect Git working tree." 2 }
if ($dirty) {
    Write-Host "Local changes detected:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    Fail "Refusing to overwrite local work. Commit or stash those changes first." 2
}

Write-Host "Updating EVAVO from verified origin/main..." -ForegroundColor Cyan
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { Fail "git pull --ff-only origin main failed." 3 }

# Resolve a Python 3.10+ interpreter for the stdlib-only structural preflight and,
# when necessary, creation of the repository-local virtual environment. An
# existing EVAVO venv can bootstrap itself even if `python` is not on PATH.
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvCreated = $false
if (Test-Path $venvPython) {
    $bootstrapPython = (Resolve-Path $venvPython).Path
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { Fail "Python 3.10+ was not found and .venv does not exist." 2 }
    $bootstrapPython = $pythonCommand.Source
}

& $bootstrapPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)"
if ($LASTEXITCODE -ne 0) { Fail "Python 3.10+ is required to bootstrap EVAVO." 2 }
Write-Host "Bootstrap Python: $bootstrapPython" -ForegroundColor Cyan

# Verify source/PowerShell/compatibility structure before pip is allowed to
# mutate even the isolated venv. This verifier path is stdlib-only.
Write-Host "Running pre-dependency structural verification..." -ForegroundColor Cyan
& $bootstrapPython (Join-Path $PSScriptRoot "verify-evavo.py") --require-powershell
if ($LASTEXITCODE -ne 0) {
    Fail "Structural verification failed before dependency installation; no pip mutation was attempted." 3
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating isolated EVAVO virtual environment at .venv..." -ForegroundColor Cyan
    & $bootstrapPython -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fail "Unable to create the repository-local .venv." 3
    }
    $venvCreated = $true
}
$python = (Resolve-Path $venvPython).Path
Write-Host "Using isolated EVAVO Python: $python" -ForegroundColor Cyan
& $python --version
if ($LASTEXITCODE -ne 0) { Fail "EVAVO .venv Python failed to run." 2 }

if ($SkipDependencies -and $venvCreated) {
    Fail "-SkipDependencies cannot be used when .venv had to be created; install the repository dependencies first." 3
}
if (-not $SkipDependencies) {
    Write-Host "Installing/updating EVAVO dependencies inside .venv..." -ForegroundColor Cyan
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Dependency installation inside .venv failed." 3 }
}

Write-Host "Running authoritative full repository verification..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") verify --full --require-powershell
if ($LASTEXITCODE -ne 0) {
    Fail "Full repository verification failed. No agent configuration has been changed." 3
}

Write-Host "Preparing and validating the native ComfyUI generation contract..." -ForegroundColor Cyan
$backendDoctorArgs = @(
    (Join-Path $PSScriptRoot "agent-doctor.py"),
    "--repair",
    "--skip-tests",
    "--mcp-port",
    "$McpPort"
)
if (-not $SkipComfyUIProvision) { $backendDoctorArgs += "--provision" }
& $python @backendDoctorArgs
$backendDoctorCode = $LASTEXITCODE
$dependencyRecoveryStatus = "not_needed"

# Make at most one evidence-gated core dependency recovery attempt, then prove
# the real generation contract again. No force sync, package guessing or
# custom-node-as-core mutation is admitted here.
if ($backendDoctorCode -ne 0 -and -not $SkipComfyUIDependencyRepair) {
    Write-Host "Strict doctor failed; checking for evidence-gated ComfyUI dependency recovery..." -ForegroundColor Yellow
    & $python (Join-Path $PSScriptRoot "recover-comfyui.py") --json
    $recoveryCode = $LASTEXITCODE
    if ($recoveryCode -eq 0) {
        $dependencyRecoveryStatus = "repaired"
        Write-Host "Dependency recovery returned success; rerunning strict agent doctor..." -ForegroundColor Cyan
        & $python @backendDoctorArgs
        $backendDoctorCode = $LASTEXITCODE
    }
    else {
        $dependencyRecoveryStatus = "not_admitted_or_failed"
        Write-Host "No admissible automatic core dependency repair completed. Strict doctor remains authoritative." -ForegroundColor Yellow
    }
}
elseif ($backendDoctorCode -ne 0 -and $SkipComfyUIDependencyRepair) {
    $dependencyRecoveryStatus = "disabled"
}

if ($backendDoctorCode -ne 0) {
    if ($SkipComfyUIProvision -and $SkipComfyUIDependencyRepair) {
        Fail "Native ComfyUI readiness failed while both provisioning and dependency repair were disabled." 3
    }
    if ($SkipComfyUIProvision) {
        Fail "Native ComfyUI readiness failed while provisioning was disabled; evidence-gated recovery did not restore the contract." 3
    }
    if ($SkipComfyUIDependencyRepair) {
        Fail "Native ComfyUI readiness failed while evidence-gated dependency repair was disabled." 3
    }
    Fail "Native ComfyUI provisioning/dependency repair or active generation-contract validation failed." 3
}

Write-Host "Bootstrapping the verified native generation backend..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") bootstrap --skip-pull --skip-verify
$code = $LASTEXITCODE
if ($code -ne 0) {
    Fail "EVAVO strict native bootstrap failed with exit code $code. Review doctor output and .evavo logs." $code
}

# A healthy port + compatible workflow is not execution proof. Prove the real
# renderer before persistent Claude/Startup configuration is changed.
Write-Host "Running real native generation smoke proof before agent configuration..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "real-generation-smoke.py") --json
if ($LASTEXITCODE -ne 0) {
    Fail "Real native generation smoke proof failed. Agent configuration was not changed." 3
}

if (-not $SkipAgentConfiguration) {
    Write-Host "Installing/updating Claude Desktop stdio MCP configuration..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-CLAUDE-MCP.ps1") -SkipValidation
    if ($LASTEXITCODE -ne 0) { Fail "Claude MCP configuration failed." 3 }

    Write-Host "Installing/updating per-user private HTTP MCP autostart..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-AGENT-MCP-AUTOSTART.ps1") -Port $McpPort -SkipValidation
    if ($LASTEXITCODE -ne 0) { Fail "HTTP MCP autostart installation failed." 3 }
}

# Recheck after configuration writes without reopening provisioning/recovery.
Write-Host "Running final agent doctor..." -ForegroundColor Cyan
$finalDoctorArgs = @(
    (Join-Path $PSScriptRoot "agent-doctor.py"),
    "--repair",
    "--skip-tests",
    "--mcp-port",
    "$McpPort"
)
& $python @finalDoctorArgs
if ($LASTEXITCODE -ne 0) {
    Fail "Agent doctor found a blocking generation-contract problem after agent configuration." 3
}

Write-Host "Running final backend status..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") status
if ($LASTEXITCODE -ne 0) { Fail "Final backend status failed." 3 }

# Cloud ChatGPT cannot directly reach workstation localhost. When an OpenAI
# Secure MCP Tunnel ID is already configured, finish that outbound bridge.
$tunnelStatePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
$tunnelId = [string]$env:EVAVO_OPENAI_TUNNEL_ID
if (-not $tunnelId -and (Test-Path $tunnelStatePath)) {
    try {
        $tunnelState = Get-Content $tunnelStatePath -Raw | ConvertFrom-Json
        $tunnelId = [string]$tunnelState.tunnel_id
    }
    catch { Fail "Existing ChatGPT tunnel state is invalid. Remove .evavo\chatgpt-tunnel.json or re-run the tunnel installer." 3 }
}

$chatGptTunnelStatus = "not_configured"
if (-not $SkipChatGPTTunnel -and $tunnelId) {
    Write-Host "Configuring OpenAI Secure MCP Tunnel for ChatGPT..." -ForegroundColor Cyan
    $tunnelInstall = @{ TunnelId = $tunnelId; McpPort = $McpPort; SkipDoctor = $true }
    if (-not $SkipAgentConfiguration) { $tunnelInstall["SkipLocalMcpInstall"] = $true }
    $persistRequested = Test-Truthy $env:EVAVO_PERSIST_OPENAI_TUNNEL_KEY
    if ($persistRequested -and $env:CONTROL_PLANE_API_KEY) { $tunnelInstall["PersistRuntimeKey"] = $true }
    & (Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL.ps1") @tunnelInstall
    if ($LASTEXITCODE -ne 0) { Fail "ChatGPT Secure MCP Tunnel profile installation failed." 3 }

    $secureKeyPath = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi" } else { $null }
    $hasDpapiKey = $secureKeyPath -and (Test-Path $secureKeyPath)
    $hasProcessKey = [bool]$env:CONTROL_PLANE_API_KEY

    if ($hasDpapiKey -or $hasProcessKey) {
        Write-Host "Validating OpenAI tunnel local preflight/profile configuration..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -RequireRuntimeKey
        if ($LASTEXITCODE -ne 0) { Fail "ChatGPT tunnel doctor found a blocking profile/preflight/integrity problem." 3 }
    }

    if ($hasDpapiKey) {
        Write-Host "Installing persistent ChatGPT tunnel login autostart..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1") -SkipDoctor
        if ($LASTEXITCODE -ne 0) { Fail "ChatGPT tunnel autostart installation failed." 3 }
        & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -RequireRuntimeKey -RequireRunning
        if ($LASTEXITCODE -ne 0) { Fail "ChatGPT tunnel was configured but did not remain running." 3 }
        $chatGptTunnelStatus = "persistent_running"
    }
    elseif ($hasProcessKey) {
        Write-Host "Starting ChatGPT tunnel for the current session (runtime key is not persisted)..." -ForegroundColor Cyan
        $starter = Join-Path $PSScriptRoot "START-CHATGPT-MCP-TUNNEL.ps1"
        $quotedStarter = '"' + $starter.Replace('"', '\"') + '"'
        $argumentLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $quotedStarter -SkipDoctor"
        Start-Process -FilePath "powershell.exe" -ArgumentList $argumentLine -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null
        $deadline = (Get-Date).AddSeconds(30)
        $running = $false
        do {
            Start-Sleep -Milliseconds 500
            & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -RequireRunning -SkipControlPlane -Json *> $null
            $running = $LASTEXITCODE -eq 0
        } while (-not $running -and (Get-Date) -lt $deadline)
        if (-not $running) { Fail "ChatGPT tunnel did not remain running for the current session." 3 }
        $chatGptTunnelStatus = "session_running"
        Write-Host "For reboot persistence, run SAVE-CHATGPT-TUNNEL-KEY.ps1 and then INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1." -ForegroundColor Yellow
    }
    else {
        $chatGptTunnelStatus = "profile_ready_needs_runtime_key"
        Write-Host "ChatGPT tunnel profile is configured, but no runtime key is available, so it was not started." -ForegroundColor Yellow
        Write-Host "Set CONTROL_PLANE_API_KEY temporarily or run SAVE-CHATGPT-TUNNEL-KEY.ps1 to enable the outbound tunnel." -ForegroundColor Yellow
    }
}
elseif (-not $SkipChatGPTTunnel) {
    Write-Host "ChatGPT Secure MCP Tunnel is not configured because no OpenAI tunnel ID is available." -ForegroundColor Yellow
    Write-Host "Once a tunnel ID exists, set EVAVO_OPENAI_TUNNEL_ID=tunnel_<32 lowercase hex characters> and rerun this updater." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "EVAVO workstation setup completed." -ForegroundColor Green
Write-Host "  Verified Git origin: $origin" -ForegroundColor Green
Write-Host "  Pre-dependency structural verifier: passed" -ForegroundColor Green
Write-Host "  Isolated Python environment: $python" -ForegroundColor Green
Write-Host "  Authoritative full verifier: passed" -ForegroundColor Green
Write-Host "  All registered safety/integration suites: passed" -ForegroundColor Green
Write-Host "  Native generation contract preparation: passed" -ForegroundColor Green
Write-Host "  Evidence-gated dependency recovery: $dependencyRecoveryStatus" -ForegroundColor $(if ($dependencyRecoveryStatus -eq "repaired") { "Green" } elseif ($dependencyRecoveryStatus -eq "not_needed") { "DarkGray" } else { "Yellow" })
Write-Host "  Strict native generation bootstrap: passed" -ForegroundColor Green
Write-Host "  Real native generation smoke proof: passed before agent config writes" -ForegroundColor Green
if (-not $SkipAgentConfiguration) {
    Write-Host "  Claude stdio MCP: installed/updated" -ForegroundColor Green
    Write-Host "  Private HTTP MCP autostart: installed and started/reloaded" -ForegroundColor Green
}
if (-not $SkipComfyUIProvision) {
    Write-Host "  ComfyUI provisioning: enabled only when native runtime/model repair was needed" -ForegroundColor Green
}
Write-Host "  Final agent doctor: active generation contract + shared roots + model inventory checked" -ForegroundColor Green
if (-not $SkipChatGPTTunnel) {
    Write-Host "  ChatGPT Secure MCP Tunnel: $chatGptTunnelStatus" -ForegroundColor $(if ($chatGptTunnelStatus -match "running") { "Green" } else { "Yellow" })
}
Write-Host ""
Write-Host "Claude: restart Claude Desktop so it reloads its MCP configuration." -ForegroundColor Yellow
Write-Host "Private local MCP endpoint: http://127.0.0.1:$McpPort/mcp" -ForegroundColor Green
Write-Host "Windows login startup launches private MCP directly without rerunning the full integration suite." -ForegroundColor Green
exit 0
