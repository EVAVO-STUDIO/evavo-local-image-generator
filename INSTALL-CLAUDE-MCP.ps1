# Install/update EVAVO MCP in Claude Desktop while preserving existing MCP servers.
param(
    [string]$ServerName = "evavo-local-image-generator"
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

Write-Host "Validating EVAVO MCP before installing Claude configuration..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot "test-agent-integration.py")
if ($LASTEXITCODE -ne 0) {
    throw "Agent/MCP integration tests failed."
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
}
if ($env:EVAVO_COMFYUI_HOME) {
    $environment["EVAVO_COMFYUI_HOME"] = $env:EVAVO_COMFYUI_HOME
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
Write-Host "Restart Claude Desktop so it reloads MCP configuration." -ForegroundColor Yellow
