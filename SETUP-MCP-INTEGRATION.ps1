#Requires -Version 5.0
<#
.SYNOPSIS
Setup Claude MCP integration for EVAVO

.DESCRIPTION
Configures Claude desktop app MCP server

.EXAMPLE
.\SETUP-MCP-INTEGRATION.ps1 -Setup
#>

param(
    [switch]$Setup = $false
)

$claudeConfigPath = "$env:APPDATA\Claude"
$claudeSettingsPath = Join-Path $claudeConfigPath "claude_desktop_config.json"
$packagePath = Get-Location

Write-Host "EVAVO MCP Integration Setup" -ForegroundColor Cyan
Write-Host "===========================" -ForegroundColor Cyan
Write-Host ""

if ($Setup) {
    Write-Host "Configuring MCP integration..." -ForegroundColor Cyan

    if (-not (Test-Path $claudeConfigPath)) {
        New-Item -ItemType Directory -Path $claudeConfigPath -Force | Out-Null
    }

    $settings = @{}
    if (Test-Path $claudeSettingsPath) {
        $settings = Get-Content $claudeSettingsPath | ConvertFrom-Json
    }

    if (-not $settings.mcpServers) {
        $settings | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value @{}
    }

    $mcpServerConfig = @{
        type = "stdio"
        command = "python"
        args = @("-m", "evavo_local_image_generator.mcp_server")
        cwd = $packagePath.Path
        env = @{
            PYTHONPATH = "."
            EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE = "bee://primary/EVAVO/ImageGeneration"
            EVAVO_COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
            KOKORO_ENDPOINT = "http://127.0.0.1:8000"
            MODEL3D_ENDPOINT = "http://127.0.0.1:8889"
            TEXTURE_ENDPOINT = "http://127.0.0.1:8890"
            PARTICLE_ENDPOINT = "http://127.0.0.1:8891"
        }
    }

    $settings.mcpServers | Add-Member -MemberType NoteProperty -Name "evavo-local-image-generator" -Value $mcpServerConfig -Force

    $settings | ConvertTo-Json -Depth 10 | Set-Content $claudeSettingsPath

    Write-Host "✓ MCP configuration written to: $claudeSettingsPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Restart Claude desktop app"
    Write-Host "2. EVAVO tools should now be available"
    Write-Host "3. Test: 'Generate an image of a mountain landscape'"
} else {
    Write-Host "Run with -Setup to configure MCP integration"
}
