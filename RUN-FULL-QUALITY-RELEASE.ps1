param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [string]$ThreeDRoot = "C:\GitRepos\evavo-3d-studio",
    [string]$ThreeDWorkerEndpoint = "http://127.0.0.1:4314",
    [switch]$Require3DExecution,
    [string]$Checkpoint = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO FULL LOCAL GENERATION RELEASE" -ForegroundColor Cyan
Write-Host "Phase 1: multimodal production readiness"
Write-Host "Phase 2: expensive fixed-seed hero image A/B review"
Write-Host ""

$gateArgs = @(
    "-Mode", "full",
    "-Python", $Python,
    "-ComfyEndpoint", $ComfyEndpoint,
    "-KokoroEndpoint", $KokoroEndpoint,
    "-AtmosphereRoot", $AtmosphereRoot,
    "-ThreeDRoot", $ThreeDRoot,
    "-ThreeDWorkerEndpoint", $ThreeDWorkerEndpoint
)
if ($Require3DExecution) {
    $gateArgs += "-Require3DExecution"
}

& .\RUN-PRODUCTION-QUALITY.ps1 @gateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Full multimodal production quality gate failed. Hero A/B rendering was not started."
}

$heroArgs = @(
    "-Python", $Python,
    "-ComfyEndpoint", $ComfyEndpoint
)
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $heroArgs += @("-Checkpoint", $Checkpoint)
}

& .\RUN-HERO-QUALITY.ps1 @heroArgs
if ($LASTEXITCODE -ne 0) {
    throw "Multimodal readiness passed, but the hero image A/B review package failed."
}

Write-Host ""
Write-Host "EVAVO full local generation release evidence completed." -ForegroundColor Green
Write-Host "The automated gates are green. Final image-profile promotion still requires completing the generated human_review.csv after visual inspection."
