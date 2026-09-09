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
    if (-not $cmd) { throw "Python 3.10+ was not found." }
    $python = $cmd.Source
}

if (-not $SkipValidation) {
    Write-Host "Validating EVAVO MCP before installing Claude configuration..." -ForegroundColor Cyan
    & $python (Join-Path $PSScriptRoot "test-agent-integration.py")
    if ($LASTEXITCODE -ne 0) { throw "Agent/MCP integration tests failed." }
}

# This read-only gate always runs, including the canonical updater's fast path.
Write-Host "Validating MCP production authority before changing Claude configuration..." -ForegroundColor Cyan
$policyOutput = & $python -m evavo_local_image_generator.mcp_policy --json
if ($LASTEXITCODE -ne 0) { throw "MCP production policy is invalid. Claude configuration was not changed." }
try { $policyResult = ($policyOutput -join "`n") | ConvertFrom-Json }
catch { throw "MCP production policy returned invalid JSON. Claude configuration was not changed." }
$generationOutputDir = [string]$policyResult.policy.default_output_root
$comfyEndpoint = [string]$policyResult.policy.comfyui_endpoint
if (-not $generationOutputDir) { throw "MCP production policy did not return a validated default output root. Claude configuration was not changed." }
if (-not $comfyEndpoint) { throw "MCP production policy did not return a validated loopback ComfyUI endpoint. Claude configuration was not changed." }

$configDir = Join-Path $env:APPDATA "Claude"
$configPath = Join-Path $configDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
if (Test-Path $configPath) {
    $raw = Get-Content $configPath -Raw
    try { $config = $raw | ConvertFrom-Json }
    catch { throw "Claude Desktop config is not valid JSON: $configPath" }
    $backup = "$configPath.evavo-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Item $configPath $backup
    Write-Host "Backed up existing Claude config to: $backup" -ForegroundColor DarkGray
}
else { $config = [pscustomobject]@{} }

if (-not ($config.PSObject.Properties.Name -contains "mcpServers")) {
    $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([pscustomobject]@{})
}
elseif ($null -eq $config.mcpServers) { $config.mcpServers = [pscustomobject]@{} }

$environment = [ordered]@{
    "PYTHONPATH" = $PSScriptRoot
    "PYTHONUNBUFFERED" = "1"
    "COMFYUI_ENDPOINT" = $comfyEndpoint
    "EVAVO_GENERATION_OUTPUT_DIR" = $generationOutputDir
    "EVAVO_AUTO_PROVISION_COMFYUI" = "1"
    "EVAVO_AUTO_PROVISION_CHECKPOINT" = "1"
}

# Persist normalized MCP authority paths returned by the validator, not raw
# environment strings. This avoids relative paths changing meaning when Claude
# launches from a different working directory.
$approvedRoots = @($policyResult.policy.additional_output_roots)
if ($approvedRoots.Count -gt 0) { $environment["EVAVO_MCP_OUTPUT_ROOTS"] = ($approvedRoots -join ";") }
$ownerWorkflow = [string]$policyResult.policy.owner_workflow
if ($ownerWorkflow) { $environment["EVAVO_COMFYUI_WORKFLOW"] = $ownerWorkflow }
if ([bool]$policyResult.policy.tool_workflow_paths_allowed) {
    $toolWorkflowRoot = [string]$policyResult.policy.tool_workflow_root
    if (-not $toolWorkflowRoot) { throw "Validated tool workflow authority is enabled but no workflow root was returned." }
    $environment["EVAVO_MCP_ALLOW_WORKFLOW_PATHS"] = "1"
    $environment["EVAVO_MCP_WORKFLOW_ROOT"] = $toolWorkflowRoot
}

# Persist only other local/non-secret configuration. Signed checkpoint URLs are
# intentionally excluded because they may contain credentials/tokens.
$nonSecretEnvironment = @(
    "EVAVO_COMFYUI_HOME",
    "EVAVO_COMFYUI_PYTHON",
    "EVAVO_SHARED_MODEL_ROOTS",
    "EVAVO_COMFYUI_MODEL_ROOTS",
    "EVAVO_CHECKPOINT_FILE",
    "EVAVO_CHECKPOINT_SHA256",
    "EVAVO_CHECKPOINT_NAME",
    "EVAVO_COMFYUI_CHECKPOINT",
    "EVAVO_TASK_HISTORY",
    "EVAVO_TORCH_INDEX_URL"
)
foreach ($name in $nonSecretEnvironment) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) { $environment[$name] = $value }
}

$server = [pscustomobject][ordered]@{
    "command" = $python
    "args" = @("-m", "evavo_local_image_generator.mcp_entry", "--transport", "stdio")
    "env" = [pscustomobject]$environment
}
if ($config.mcpServers.PSObject.Properties.Name -contains $ServerName) { $config.mcpServers.$ServerName = $server }
else { $config.mcpServers | Add-Member -NotePropertyName $ServerName -NotePropertyValue $server }
$config | ConvertTo-Json -Depth 20 | Set-Content -Path $configPath -Encoding UTF8

Write-Host "Claude Desktop MCP configuration installed: $configPath" -ForegroundColor Green
Write-Host "Python: $python" -ForegroundColor Green
Write-Host "ComfyUI endpoint: $comfyEndpoint (policy-validated loopback)" -ForegroundColor Green
Write-Host "Generation output root: $generationOutputDir" -ForegroundColor Green
Write-Host "MCP launch and persisted authority are policy-validated." -ForegroundColor Green
if ($env:EVAVO_CHECKPOINT_URL) { Write-Host "EVAVO_CHECKPOINT_URL was not persisted because URLs may contain secrets." -ForegroundColor Yellow }
Write-Host "Restart Claude Desktop so it reloads MCP configuration." -ForegroundColor Yellow