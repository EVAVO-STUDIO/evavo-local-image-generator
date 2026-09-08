<#
.SYNOPSIS
Push the BeeStation integration upgrade to GitHub main branch

.DESCRIPTION
This script extracts the prepared git commit and pushes the comprehensive
BeeStation and evavo-local-storage integration upgrade to the main branch.

The upgrade includes:
- Enhanced storage.py with proper evavo-local-storage API integration
- Upgraded mcp_server.py with full BeeStation URI support
- Updated requirements.txt with httpx dependency
- Enhanced .mcp.json configuration

.EXAMPLE
.\PUSH-UPGRADE-TO-MAIN.ps1
#>

Write-Host "=== EVAVO BeeStation Integration Upgrade ===" -ForegroundColor Cyan

# Verify we're in the right directory
if (!(Test-Path ".git")) {
    Write-Host "Error: Must run from evavo-local-image-generator root directory" -ForegroundColor Red
    exit 1
}

Write-Host "📦 Extracting upgrade commit..." -ForegroundColor Yellow

# Extract the git archive (using Windows native tar if available, or fallback)
if (Get-Command tar -ErrorAction SilentlyContinue) {
    tar -xzf evavo-upgrade-commit.tar.gz
} else {
    Write-Host "tar not found, using PowerShell to extract..." -ForegroundColor Yellow
    # Fallback: use PowerShell compression module
    $ProgressPreference = 'SilentlyContinue'
    Expand-Archive -Path evavo-upgrade-commit.tar.gz -DestinationPath . -Force
}

Write-Host "✅ Commit extracted" -ForegroundColor Green

Write-Host "📊 Checking git status..." -ForegroundColor Yellow
git status

Write-Host "📝 Viewing new commit..." -ForegroundColor Yellow
git log -1 --oneline

Write-Host "🚀 Pushing to main branch..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Successfully pushed upgrade to main!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Upgrade summary:" -ForegroundColor Cyan
    Write-Host "  • Enhanced storage.py with evavo-local-storage API integration"
    Write-Host "  • Upgraded mcp_server.py with full BeeStation URI support"
    Write-Host "  • Added health_check tool for service monitoring"
    Write-Host "  • Implemented ComfyUIClient for workflow execution"
    Write-Host "  • All operations now use bee:// URIs (no Windows paths)"
    Write-Host "  • Proper digest-bound task registration"
    Write-Host ""
    Write-Host "Repository: https://github.com/EVAVO-STUDIO/evavo-local-image-generator" -ForegroundColor Cyan
} else {
    Write-Host "❌ Push failed. Please check the error above." -ForegroundColor Red
    exit 1
}
