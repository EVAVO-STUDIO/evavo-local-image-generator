# Install or remove EVAVO Streamable HTTP MCP startup for the current Windows user.
# Uses the per-user Startup folder; no administrator rights required.

param(
    [switch]$Uninstall,
    [int]$Port = 8765,
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Port -lt 1 -or $Port -gt 65535) { throw "Port must be between 1 and 65535." }
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$launcher = Join-Path $startupDir "EVAVO-Agent-MCP.cmd"
if ($Uninstall) {
    if (Test-Path $launcher) { Remove-Item -Force $launcher; Write-Host "Removed EVAVO agent MCP autostart: $launcher" -ForegroundColor Green }
    else { Write-Host "EVAVO agent MCP autostart was not installed." -ForegroundColor Yellow }
    exit 0
}

$repo = (Resolve-Path $PSScriptRoot).Path
$script = Join-Path $repo "START-AGENT-MCP.ps1"
if (-not (Test-Path $script)) { throw "Missing START-AGENT-MCP.ps1" }
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python 3.10+ was not found." }
    $python = $cmd.Source
}

if (-not $SkipValidation) {
    Write-Host "Validating EVAVO MCP before installing login autostart..." -ForegroundColor Cyan
    & $python (Join-Path $repo "test-agent-integration.py")
    if ($LASTEXITCODE -ne 0) { throw "Agent/MCP integration tests failed." }
}

# This read-only gate always runs, including the canonical updater's fast path.
Write-Host "Validating MCP production authority before changing login autostart..." -ForegroundColor Cyan
$policyOutput = & $python -m evavo_local_image_generator.mcp_policy --json
if ($LASTEXITCODE -ne 0) { throw "MCP production policy is invalid. Windows login autostart was not changed." }
try { $policyResult = ($policyOutput -join "`n") | ConvertFrom-Json }
catch { throw "MCP production policy returned invalid JSON. Windows login autostart was not changed." }
$generationOutputDir = [string]$policyResult.policy.default_output_root
$comfyEndpoint = [string]$policyResult.policy.comfyui_endpoint
if (-not $generationOutputDir) { throw "MCP production policy did not return a validated default output root. Windows login autostart was not changed." }
if (-not $comfyEndpoint) { throw "MCP production policy did not return a validated loopback ComfyUI endpoint. Windows login autostart was not changed." }

New-Item -ItemType Directory -Force -Path $startupDir | Out-Null

function ConvertTo-CmdSetLine([string]$Name, [string]$Value) {
    if (-not $Value) { return $null }
    if ($Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Cannot persist $Name into CMD autostart because its value contains an unsupported quote/newline. Configure it as a Windows user environment variable instead."
    }
    $safe = $Value.Replace('%', '%%')
    return "set `"$Name=$safe`""
}

$persistedEnvironment = [ordered]@{
    "EVAVO_AUTO_PROVISION_COMFYUI" = "1"
    "EVAVO_AUTO_PROVISION_CHECKPOINT" = "1"
    "COMFYUI_ENDPOINT" = $comfyEndpoint
    "EVAVO_GENERATION_OUTPUT_DIR" = $generationOutputDir
}

# Persist normalized MCP authority paths returned by the validator, not raw
# relative environment strings whose meaning could change after reboot.
$approvedRoots = @($policyResult.policy.additional_output_roots)
if ($approvedRoots.Count -gt 0) { $persistedEnvironment["EVAVO_MCP_OUTPUT_ROOTS"] = ($approvedRoots -join ";") }
$ownerWorkflow = [string]$policyResult.policy.owner_workflow
if ($ownerWorkflow) { $persistedEnvironment["EVAVO_COMFYUI_WORKFLOW"] = $ownerWorkflow }
if ([bool]$policyResult.policy.tool_workflow_paths_allowed) {
    $toolWorkflowRoot = [string]$policyResult.policy.tool_workflow_root
    if (-not $toolWorkflowRoot) { throw "Validated tool workflow authority is enabled but no workflow root was returned." }
    $persistedEnvironment["EVAVO_MCP_ALLOW_WORKFLOW_PATHS"] = "1"
    $persistedEnvironment["EVAVO_MCP_WORKFLOW_ROOT"] = $toolWorkflowRoot
}

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
    if ($value) { $persistedEnvironment[$name] = $value }
}

$envLines = New-Object System.Collections.Generic.List[string]
foreach ($entry in $persistedEnvironment.GetEnumerator()) {
    $line = ConvertTo-CmdSetLine $entry.Key ([string]$entry.Value)
    if ($line) { $envLines.Add($line) }
}
$escapedRepo = $repo.Replace('"', '""')
$escapedScript = $script.Replace('"', '""')
$environmentBlock = ($envLines -join "`r`n")
$cmd = @"
@echo off
$environmentBlock
cd /d "$escapedRepo"
start "EVAVO Agent MCP" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$escapedScript" -Port $Port -SkipValidation
"@
Set-Content -Path $launcher -Value $cmd -Encoding ASCII

Write-Host "Installed EVAVO agent MCP autostart: $launcher" -ForegroundColor Green
Write-Host "ComfyUI endpoint: $comfyEndpoint (policy-validated loopback)" -ForegroundColor Green
Write-Host "Generation output root: $generationOutputDir" -ForegroundColor Green
Write-Host "MCP launch and persisted authority are policy-validated." -ForegroundColor Green
if ($env:EVAVO_CHECKPOINT_URL) { Write-Host "EVAVO_CHECKPOINT_URL was not persisted because URLs may contain secrets." -ForegroundColor Yellow }

Write-Host "Starting/reloading it now in a hidden process..." -ForegroundColor Cyan
$quotedScript = '"' + $script.Replace('"', '\"') + '"'
$argumentLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $quotedScript -Port $Port -SkipValidation -RestartIfRunning"
Start-Process -FilePath "powershell.exe" -ArgumentList $argumentLine -WorkingDirectory $repo -WindowStyle Hidden | Out-Null

$deadline = (Get-Date).AddSeconds(20)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(300) -and $client.Connected) {
            $client.EndConnect($iar); $client.Close(); $ready = $true; break
        }
        $client.Close()
    } catch {}
    Start-Sleep -Milliseconds 250
}
if (-not $ready) { throw "EVAVO MCP did not begin listening on port $Port within 20 seconds. Run START-AGENT-MCP.ps1 manually for diagnostics." }
Write-Host "EVAVO MCP is listening at http://127.0.0.1:$Port/mcp" -ForegroundColor Green