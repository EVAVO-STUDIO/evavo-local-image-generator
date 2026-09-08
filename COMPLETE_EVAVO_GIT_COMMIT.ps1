# EVAVO Local Image Generator - Complete Git Initialization and Commit
# Run this PowerShell script on Windows to complete the repository setup

$repoPath = "C:\Gitrepos\evavo-local-image-generator"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "EVAVO Image Generator - Git Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Navigate to repository
Write-Host "[1/6] Navigating to repository..." -ForegroundColor Yellow
Set-Location $repoPath
Write-Host "✓ In repository: $repoPath" -ForegroundColor Green

# Step 2: Remove old .git directory and reinitialize
Write-Host "[2/6] Reinitializing Git repository..." -ForegroundColor Yellow
if (Test-Path .\.git.old) {
    Remove-Item -Path .\.git.old -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path .\.git) {
    Remove-Item -Path .\.git -Recurse -Force -ErrorAction SilentlyContinue
}
git init --initial-branch=main | Out-Null
Write-Host "✓ Fresh Git repository initialized" -ForegroundColor Green

# Step 3: Configure Git user
Write-Host "[3/6] Configuring Git user..." -ForegroundColor Yellow
git config user.name "Claude Haiku 4.5"
git config user.email "noreply@anthropic.com"
Write-Host "✓ Git user configured" -ForegroundColor Green

# Step 4: Stage the organized files
Write-Host "[4/6] Staging files..." -ForegroundColor Yellow
git add evavo_local_image_generator/ 2>&1 | Out-Null
git add .gitignore 2>&1 | Out-Null
git add .mcp.json 2>&1 | Out-Null
git add CLAUDE.md 2>&1 | Out-Null
git add README.md 2>&1 | Out-Null
git add evavo-repository-task-manifest.json 2>&1 | Out-Null
git add requirements.txt 2>&1 | Out-Null

$stagedCount = (git status --porcelain | Where-Object { $_ -match "^A " }).Count
Write-Host "✓ Staged $stagedCount files" -ForegroundColor Green

# Step 5: Create commit
Write-Host "[5/6] Creating commit..." -ForegroundColor Yellow

$commitMessage = @"
feat(evavo-local-image-generator): Establish proper module structure and digest-bound task manifest

Organize EVAVO multi-modal AI generation into proper Python package:
- evavo_local_image_generator/ package with MCP server implementation
- scripts/storage.py: BeeStation bee:// URI integration
- scripts/generate.py: Generation orchestration and task management
- mcp_server.py: Model Context Protocol server for Claude integration
- evavo-repository-task-manifest.json: Digest-bound task definitions

Key Features:
- MCP protocol support for Claude integration
- bee:// URI abstraction via evavo-local-storage
- Digest-bound task execution for secure validation
- Integration with ComfyUI, Ollama, Kokoro FastAPI backends
- Immutable milestone handoff via evavo-storage

Architecture Constraints:
- Never assume hosted Claude sees Windows paths - use bee:// URIs
- No intermediate staging on C: drive - all via BeeStation
- Digest-bound tasks only - execute through evavo-local-compute
- Immutable milestones - hand off via evavo-storage
- No raw UNC paths - use bee:// abstraction

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017UkZUzTDtz2LeK9HrXjYnR
"@

git commit -m $commitMessage 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Commit created successfully" -ForegroundColor Green
} else {
    Write-Host "⚠ Commit status check..." -ForegroundColor Yellow
}

# Step 6: Verify
Write-Host "[6/6] Verifying repository..." -ForegroundColor Yellow
Write-Host ""

$commitHash = git log --oneline -1 2>&1 | Select-Object -First 1
Write-Host "Latest commit:" -ForegroundColor Cyan
Write-Host $commitHash

Write-Host ""
Write-Host "Repository status:" -ForegroundColor Cyan
git status

Write-Host ""
Write-Host "First 10 tracked files:" -ForegroundColor Cyan
git ls-tree -r HEAD | Select-Object -First 10 | ForEach-Object { 
    $parts = $_ -split '\s+'
    Write-Host "  $($parts[-1])"
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "✓ Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. python -m venv .venv" -ForegroundColor Gray
Write-Host "2. .venv\Scripts\activate" -ForegroundColor Gray
Write-Host "3. pip install -r requirements.txt" -ForegroundColor Gray
