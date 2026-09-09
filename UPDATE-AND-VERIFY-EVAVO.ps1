# EVAVO Local Image Generator - update, install, validate, configure agents and verify
# Safe by default: refuses to overwrite local Git changes and only fast-forwards main.

param(
    [switch]$SkipDependencies,
    [switch]$SkipAgentConfiguration,
    [switch]$SkipComfyUIProvision,
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

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne "main") {
    Fail "Repository must be on branch main. Current branch: $branch" 2
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    Fail "Unable to inspect Git working tree." 2
}
if ($dirty) {
    Write-Host "Local changes detected:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    Fail "Refusing to overwrite local work. Commit or stash those changes first." 2
}

Write-Host "Updating EVAVO from origin/main..." -ForegroundColor Cyan
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    Fail "git pull --ff-only origin main failed." 3
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Fail "Python 3.10+ was not found." 2
    }
    $python = $pythonCommand.Source
}

Write-Host "Using Python: $python" -ForegroundColor Cyan
& $python --version
if ($LASTEXITCODE -ne 0) {
    Fail "Python failed to run." 2
}

if (-not $SkipDependencies) {
    Write-Host "Installing/updating EVAVO dependencies..." -ForegroundColor Cyan
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Fail "Dependency installation failed." 3
    }
}

Write-Host "Running provisioning/runtime safety tests..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-provisioning.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Provisioning/runtime safety tests failed." 3
}

Write-Host "Running backend automation/MCP file-boundary tests..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-backend-automation.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Backend automation/MCP file-boundary tests failed." 3
}

Write-Host "Running ChatGPT tunnel security-contract tests..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-chatgpt-tunnel.py")
if ($LASTEXITCODE -ne 0) {
    Fail "ChatGPT tunnel security-contract tests failed." 3
}

Write-Host "Running Claude/ChatGPT MCP transport validation..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-agent-integration.py")
if ($LASTEXITCODE -ne 0) {
    Fail "Agent/MCP integration tests failed." 3
}

Write-Host "Running EVAVO bootstrap..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") bootstrap --skip-pull
$code = $LASTEXITCODE
if ($code -ne 0) {
    Fail "EVAVO bootstrap failed with exit code $code. Review doctor output and .evavo logs." $code
}

if (-not $SkipAgentConfiguration) {
    Write-Host "Installing/updating Claude Desktop stdio MCP configuration..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-CLAUDE-MCP.ps1") -SkipValidation
    if ($LASTEXITCODE -ne 0) {
        Fail "Claude MCP configuration failed." 3
    }

    Write-Host "Installing/updating per-user HTTP MCP autostart..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "INSTALL-AGENT-MCP-AUTOSTART.ps1") -Port $McpPort -SkipValidation
    if ($LASTEXITCODE -ne 0) {
        Fail "HTTP MCP autostart installation failed." 3
    }
}

Write-Host "Running final agent doctor with safe repair enabled..." -ForegroundColor Cyan
$doctorArgs = @((Join-Path $PSScriptRoot "agent-doctor.py"), "--repair", "--skip-tests", "--mcp-port", "$McpPort")
if (-not $SkipComfyUIProvision) {
    $doctorArgs += "--provision"
}
& $python @doctorArgs
if ($LASTEXITCODE -ne 0) {
    Fail "Agent doctor found a blocking configuration problem. Configure a checkpoint source/shared model root if required, then rerun." 3
}

Write-Host "Running final backend status..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "evavo.py") status
if ($LASTEXITCODE -ne 0) {
    Fail "Final backend status failed." 3
}

# ChatGPT cloud cannot directly reach workstation localhost. When an OpenAI
# Secure MCP Tunnel ID is already configured, finish that bridge automatically.
$tunnelStatePath = Join-Path $PSScriptRoot ".evavo\chatgpt-tunnel.json"
$tunnelId = [string]$env:EVAVO_OPENAI_TUNNEL_ID
if (-not $tunnelId -and (Test-Path $tunnelStatePath)) {
    try {
        $tunnelState = Get-Content $tunnelStatePath -Raw | ConvertFrom-Json
        $tunnelId = [string]$tunnelState.tunnel_id
    }
    catch {
        Fail "Existing ChatGPT tunnel state is invalid. Remove .evavo\chatgpt-tunnel.json or re-run the tunnel installer." 3
    }
}

$chatGptTunnelStatus = "not_configured"
if (-not $SkipChatGPTTunnel -and $tunnelId) {
    Write-Host "Configuring OpenAI Secure MCP Tunnel for ChatGPT..." -ForegroundColor Cyan
    $tunnelInstall = @{
        TunnelId = $tunnelId
        McpPort = $McpPort
        SkipDoctor = $true
    }
    if (-not $SkipAgentConfiguration) {
        $tunnelInstall["SkipLocalMcpInstall"] = $true
    }

    $persistRequested = Test-Truthy $env:EVAVO_PERSIST_OPENAI_TUNNEL_KEY
    if ($persistRequested -and $env:CONTROL_PLANE_API_KEY) {
        $tunnelInstall["PersistRuntimeKey"] = $true
    }
    & (Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL.ps1") @tunnelInstall
    if ($LASTEXITCODE -ne 0) {
        Fail "ChatGPT Secure MCP Tunnel profile installation failed." 3
    }

    $secureKeyPath = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi" } else { $null }
    $hasDpapiKey = $secureKeyPath -and (Test-Path $secureKeyPath)
    $hasProcessKey = [bool]$env:CONTROL_PLANE_API_KEY

    if ($hasDpapiKey -or $hasProcessKey) {
        Write-Host "Validating OpenAI tunnel control-plane/profile configuration..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -RequireRuntimeKey
        if ($LASTEXITCODE -ne 0) {
            Fail "ChatGPT tunnel doctor found a blocking profile/control-plane problem." 3
        }
    }

    if ($hasDpapiKey) {
        Write-Host "Installing persistent ChatGPT tunnel login autostart..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1") -SkipDoctor
        if ($LASTEXITCODE -ne 0) {
            Fail "ChatGPT tunnel autostart installation failed." 3
        }
        & (Join-Path $PSScriptRoot "CHATGPT-TUNNEL-DOCTOR.ps1") -RequireRuntimeKey -RequireRunning
        if ($LASTEXITCODE -ne 0) {
            Fail "ChatGPT tunnel was configured but did not remain running." 3
        }
        $chatGptTunnelStatus = "persistent_running"
    }
    elseif ($hasProcessKey) {
        # Connect now for this Windows session without persisting the plaintext
        # runtime key. The child tunnel-client inherits the temporary key.
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
        if (-not $running) {
            Fail "ChatGPT tunnel did not remain running for the current session." 3
        }
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
    Write-Host "Once a tunnel ID exists, set EVAVO_OPENAI_TUNNEL_ID=tunnel_... and rerun this updater." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "EVAVO workstation setup completed." -ForegroundColor Green
Write-Host "  Dependencies: installed/validated" -ForegroundColor Green
Write-Host "  Provisioning/runtime safety tests: passed" -ForegroundColor Green
Write-Host "  Backend repair/file-boundary tests: passed" -ForegroundColor Green
Write-Host "  ChatGPT tunnel security-contract tests: passed" -ForegroundColor Green
Write-Host "  Operational tests: passed" -ForegroundColor Green
Write-Host "  MCP negotiation/generation/model-inventory tests: passed" -ForegroundColor Green
if (-not $SkipAgentConfiguration) {
    Write-Host "  Claude stdio MCP: installed/updated" -ForegroundColor Green
    Write-Host "  Private HTTP MCP autostart: installed and started" -ForegroundColor Green
}
if (-not $SkipComfyUIProvision) {
    Write-Host "  ComfyUI provisioning: enabled when missing" -ForegroundColor Green
}
Write-Host "  Agent doctor: real renderer + checkpoint + shared roots + model inventory checked" -ForegroundColor Green
if (-not $SkipChatGPTTunnel) {
    Write-Host "  ChatGPT Secure MCP Tunnel: $chatGptTunnelStatus" -ForegroundColor $(if ($chatGptTunnelStatus -match "running") { "Green" } else { "Yellow" })
}
Write-Host ""
Write-Host "Claude: restart Claude Desktop so it reloads its MCP configuration." -ForegroundColor Yellow
Write-Host "Private local MCP endpoint: http://127.0.0.1:$McpPort/mcp" -ForegroundColor Green
Write-Host "Windows login startup launches private MCP directly without rerunning the full integration suite." -ForegroundColor Green
exit 0
