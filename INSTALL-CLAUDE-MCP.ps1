# Install/update EVAVO MCP in Claude Desktop while preserving existing MCP servers.
param(
    [string]$ServerName = "evavo-local-image-generator",
    [switch]$SkipValidation
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

if (-not $SkipValidation) {
    Write-Host "Validating EVAVO MCP before installing Claude configuration..." -ForegroundColor Cyan
    & $python (Join-Path $PSScriptRoot "test-agent-integration.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Agent/MCP integration tests failed."
    }
}

$configDir = Join-Path $env:APPDATA "Claude"
$configPath = Join-Path $configDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

if (Test-Path $configPath) {
    $raw = Get-Content $configPath -Raw
    try {
        $config = $raw | ConvertFrom-Json
    }
    catch {
        throw "Claude Desktop config is not valid JSON: $configPath"
    }

    $backup = "$configPath.evavo-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item $configPath $backup
    Write-Host "Backed up existing Claude config to: $backup" -ForegroundColor DarkGray
}
else {
    $config = [pscustomobject]@{}
}

if (-not ($config.PSObject.Properties.Name -contains "mcpServers")) {
    $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([pscustomobject]@{})
}
elseif ($null -eq $config.mcpServers) {
    $config.mcpServers = [pscustomobject]@{}
}

$environment = [ordered]@{
    "PYTHONPATH" = $PSScriptRoot
    "PYTHONUNBUFFERED" = "1"
    "EVAVO_COMFYUI_ENDPOINT" = "http://127.0.0.1:8188"
    "EVAVO_GENERATION_OUTPUT_DIR" = (Join-Path $PSScriptRoot ".evavo\outputs")
    "EVAVO_AUTO_PROVISION_COMFYUI" = "1"
    "EVAVO_AUTO_PROVISION_CHECKPOINT" = "1"
}

# Persist only local/non-secret configuration into Claude Desktop. In
# particular, EVAVO_CHECKPOINT_URL is intentionally not copied because signed
# model URLs can contain credentials/tokens in plaintext.
$nonSecretEnvironment = @(
    "EVAVO_COMFYUI_HOME",
    "EVAVO_COMFYUI_PYTHON",
    "EVAVO_SHARED_MODEL_ROOTS",
    "EVAVO_COMFYUI_MODEL_ROOTS",
    "EVAVO_CHECKPOINT_FILE",
    "EVAVO_CHECKPOINT_SHA256",
    "EVAVO_CHECKPOINT_NAME",
    "EVAVO_COMFYUI_WORKFLOW",
    "EVAVO_COMFYUI_CHECKPOINT",
    "EVAVO_TASK_HISTORY",
    "EVAVO_TORCH_INDEX_URL",
    "EVAVO_MCP_OUTPUT_ROOTS",
    "EVAVO_MCP_ALLOW_WORKFLOW_PATHS",
    "EVAVO_MCP_WORKFLOW_ROOT"
)
foreach ($name in $nonSecretEnvironment) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) {
        $environment[$name] = $value
    }
}

$server = [pscustomobject][ordered]@{
    "command" = $python
    "args" = @("-m", "evavo_local_image_generator.mcp_server", "--transport", "stdio")
    "env" = [pscustomobject]$environment
}

if ($config.mcpServers.PSObject.Properties.Name -contains $ServerName) {
    $config.mcpServers.$ServerName = $server
}
else {
    $config.mcpServers | Add-Member -NotePropertyName $ServerName -NotePropertyValue $server
}

$config | ConvertTo-Json -Depth 20 | Set-Content -Path $configPath -Encoding UTF8

Write-Host "Claude Desktop MCP configuration installed:" -ForegroundColor Green
Write-Host "  $configPath" -ForegroundColor Green
Write-Host "Server: $ServerName" -ForegroundColor Green
Write-Host "Python: $python" -ForegroundColor Green
Write-Host "Repo:   $PSScriptRoot" -ForegroundColor Green
Write-Host "Backend/checkpoint auto-provision: enabled (operator-controlled model sources only)" -ForegroundColor Green
Write-Host "MCP file policy: output/workflow paths remain owner-confined; configured non-secret roots are persisted." -ForegroundColor Green
if ($env:EVAVO_SHARED_MODEL_ROOTS -or $env:EVAVO_COMFYUI_MODEL_ROOTS) {
    Write-Host "Shared ComfyUI model roots: persisted into Claude MCP environment" -ForegroundColor Green
}
if ($env:EVAVO_CHECKPOINT_URL) {
    Write-Host "Note: EVAVO_CHECKPOINT_URL was not persisted into Claude config because URLs may contain secrets." -ForegroundColor Yellow
}
Write-Host "Restart Claude Desktop so it reloads MCP configuration." -ForegroundColor Yellow
