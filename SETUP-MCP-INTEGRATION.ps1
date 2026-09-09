# Compatibility shim for the historical Claude MCP setup entry point.
# The canonical installer preserves existing MCP servers, resolves absolute
# Python/repository paths, and validates the current MCP v2 contract.

param(
    [switch]$Setup,
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$installer = Join-Path $PSScriptRoot "INSTALL-CLAUDE-MCP.ps1"
if (-not (Test-Path $installer)) {
    throw "Canonical Claude installer is missing: $installer"
}

if (-not $Setup) {
    Write-Host "SETUP-MCP-INTEGRATION.ps1 is a compatibility shim." -ForegroundColor Yellow
    Write-Host "Routing to INSTALL-CLAUDE-MCP.ps1. The old Kokoro/3D/texture/particle MCP configuration is retired." -ForegroundColor Yellow
}

$arguments = @{}
if ($SkipValidation) {
    $arguments["SkipValidation"] = $true
}
& $installer @arguments
exit $LASTEXITCODE
