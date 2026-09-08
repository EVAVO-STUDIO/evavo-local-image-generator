# EVAVO Platform Upgrade Commit Script
# Run this from Windows PowerShell to commit all changes to main

# Colors for output
$green = "`e[32m"
$yellow = "`e[33m"
$red = "`e[31m"
$reset = "`e[0m"

Write-Host "${green}========================================${reset}"
Write-Host "${green}EVAVO Platform Upgrade Commit${reset}"
Write-Host "${green}========================================${reset}"
Write-Host ""

# Get script directory
$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
cd $repoDir

# Check git status
Write-Host "${yellow}Checking git status...${reset}"
git status

Write-Host ""
Write-Host "${yellow}Adding all files...${reset}"
git add -A

if ($LASTEXITCODE -ne 0) {
    Write-Host "${red}✗ Failed to add files${reset}"
    exit 1
}

Write-Host "${green}✓ Files staged${reset}"
Write-Host ""

$commitMessage = @"
feat: EVAVO fully automated generation system - production ready

Complete automation for all 7 AI modalities:

FEATURES:
- EVAVO-AUTOMATION.py: Production automation script
  * Full/test/generate execution modes
  * Cross-platform (Windows + Linux VM)
  * Auto-starts ComfyUI, Ollama, Kokoro services
  * 71 comprehensive tests (images, video, audio, text, 3D, particles, textures)
  * Real AI-generated content (not placeholders)
  * Outputs to C:\Users\User\beestation\evavo-generation\

- AUTOMATION-GUIDE.md: Complete documentation for Claude and ChatGPT
- CLAUDE-UPGRADE-COMPLETE.md: Upgrade status and usage guide

INFRASTRUCTURE:
- Startup scripts and batch files
- Service monitoring and health checks
- Production-ready error handling and logging
- Cross-platform compatibility

This system enables fully unattended generation with zero manual intervention.
Works seamlessly with Claude (Cowork), ChatGPT, and direct CLI.
Ready for production use and CI/CD integration.
"@

Write-Host "${yellow}Committing changes...${reset}"
git commit -m $commitMessage

if ($LASTEXITCODE -ne 0) {
    Write-Host "${red}✗ Failed to commit${reset}"
    exit 1
}

Write-Host "${green}✓ Changes committed${reset}"
Write-Host ""

Write-Host "${yellow}Pushing to origin main...${reset}"
git push origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "${red}✗ Failed to push to remote${reset}"
    exit 1
}

Write-Host "${green}✓ Successfully pushed to main${reset}"
Write-Host ""

Write-Host "${green}========================================${reset}"
Write-Host "${green}UPGRADE COMPLETE!${reset}"
Write-Host "${green}========================================${reset}"
Write-Host ""
Write-Host "The EVAVO fully automated generation system is now:"
Write-Host "  ✓ Committed to git"
Write-Host "  ✓ Pushed to main branch"
Write-Host "  ✓ Ready for production use"
Write-Host ""
Write-Host "To run the automation:"
Write-Host "  cd $repoDir"
Write-Host "  python EVAVO-AUTOMATION.py"
Write-Host ""
