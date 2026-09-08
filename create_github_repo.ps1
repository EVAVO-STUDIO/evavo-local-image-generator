# GitHub Repository Creation Script
$org = "EVAVO-STUDIO"
$repo = "evavo-local-image-generator"
$description = "EVAVO Local Image Generator - Multi-modal AI generation system with digest-bound task execution"

# Check if gh CLI is available in PATH or common locations
$ghPaths = @(
    "gh",
    "C:\Program Files\GitHub CLI\gh.exe",
    "C:\Program Files (x86)\GitHub CLI\gh.exe",
    "$env:LOCALAPPDATA\Programs\gh\gh.exe"
)

$ghFound = $false
foreach ($path in $ghPaths) {
    try {
        if (Test-Path $path) {
            $ghFound = $true
            $ghCmd = $path
            Write-Host "✓ Found GitHub CLI at: $path"
            break
        }
    } catch {
        # Continue to next path
    }
}

if ($ghFound) {
    Write-Host ""
    Write-Host "=== Creating GitHub Repository ===" 
    Write-Host "Organization: $org"
    Write-Host "Repository: $repo"
    Write-Host ""
    
    # Create repository using gh CLI
    & $ghCmd repo create "$org/$repo" --public --description "$description" --source=. --remote=origin --push
    
    Write-Host ""
    Write-Host "✓ Repository created and pushed successfully!"
} else {
    Write-Host "✗ GitHub CLI not found in common locations"
    Write-Host ""
    Write-Host "To complete the setup, please:"
    Write-Host "1. Download GitHub CLI from: https://cli.github.com/"
    Write-Host "2. Run: gh repo create EVAVO-STUDIO/evavo-local-image-generator --public --source=. --remote=origin --push"
    Write-Host ""
    Write-Host "Or create repository manually at: https://github.com/organizations/EVAVO-STUDIO/repositories/new"
}
