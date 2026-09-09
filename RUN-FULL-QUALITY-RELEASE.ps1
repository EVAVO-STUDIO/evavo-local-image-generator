param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$GatewayEndpoint = "http://127.0.0.1:8000",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [string]$ThreeDRoot = "C:\GitRepos\evavo-3d-studio",
    [string]$ThreeDWorkerEndpoint = "http://127.0.0.1:4314",
    [switch]$RequireGateway,
    [switch]$Require3DExecution,
    [string]$Checkpoint = "",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO FULL LOCAL GENERATION RELEASE" -ForegroundColor Cyan
Write-Host "Phase 1: multimodal production readiness"
Write-Host "Phase 2: expensive fixed-seed hero image A/B review + model/runtime attestation"
Write-Host ""

$gateArgs = @(
    "-Mode", "full",
    "-Python", $Python,
    "-ComfyEndpoint", $ComfyEndpoint,
    "-KokoroEndpoint", $KokoroEndpoint,
    "-GatewayEndpoint", $GatewayEndpoint,
    "-AtmosphereRoot", $AtmosphereRoot,
    "-ThreeDRoot", $ThreeDRoot,
    "-ThreeDWorkerEndpoint", $ThreeDWorkerEndpoint
)
if ($RequireGateway) {
    $gateArgs += "-RequireGateway"
}
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
if (-not [string]::IsNullOrWhiteSpace($ComfyRoot)) {
    $heroArgs += @("-ComfyRoot", $ComfyRoot)
}
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $heroArgs += @("-Checkpoint", $Checkpoint)
}
if ($AllowPartialRuntimeEvidence) {
    $heroArgs += "-AllowPartialRuntimeEvidence"
}

& .\RUN-HERO-QUALITY.ps1 @heroArgs
if ($LASTEXITCODE -ne 0) {
    throw "Multimodal readiness passed, but the hero image A/B review/attestation package failed."
}

Write-Host ""
Write-Host "EVAVO full local generation release evidence completed." -ForegroundColor Green
if ($RequireGateway) {
    Write-Host "Gateway image round-trip proof: required and passed." -ForegroundColor Green
}
if ($Require3DExecution) {
    Write-Host "3D bounded execution-worker proof: required and passed." -ForegroundColor Green
}
Write-Host "The automated gates and runtime/model evidence are green. Final image-profile and voice promotion still require completing the generated human review sheets after visual/listening inspection."
