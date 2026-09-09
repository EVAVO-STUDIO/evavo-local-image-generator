param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$KokoroRoot = "C:\AI\Kokoro-FastAPI",
    [string]$GatewayEndpoint = "http://127.0.0.1:8000",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [string]$ThreeDRoot = "C:\GitRepos\evavo-3d-studio",
    [string]$ThreeDWorkerEndpoint = "http://127.0.0.1:4314",
    [switch]$RequireGateway,
    [switch]$Require3DExecution,
    [string]$Checkpoint = "",
    [string]$ReleaseRoot = "",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$releaseStarted = Get-Date
$releaseStamp = $releaseStarted.ToString("yyyyMMdd-HHmmss")
if ([string]::IsNullOrWhiteSpace($ReleaseRoot)) {
    $ReleaseRoot = Join-Path $PSScriptRoot ".evavo\quality-results\full-release\$releaseStamp"
} elseif ([System.IO.Path]::IsPathRooted($ReleaseRoot)) {
    $ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
} else {
    $ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $ReleaseRoot))
}

if (Test-Path -LiteralPath $ReleaseRoot) {
    $existing = @(Get-ChildItem -LiteralPath $ReleaseRoot -Force -ErrorAction Stop)
    if ($existing.Count -gt 0) {
        throw "ReleaseRoot must be empty so evidence from different runs cannot be mixed: $ReleaseRoot"
    }
} else {
    New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
}

Write-Host "EVAVO FULL LOCAL GENERATION RELEASE" -ForegroundColor Cyan
Write-Host "Release root: $ReleaseRoot"
Write-Host "Phase 1: multimodal production readiness + sibling runtime attestation"
Write-Host "Phase 2: expensive fixed-seed hero image A/B review + model/runtime attestation"
Write-Host "Phase 3: tamper-evident evidence manifest"
Write-Host ""

$gateArgs = @(
    "-Mode", "full",
    "-Python", $Python,
    "-ComfyEndpoint", $ComfyEndpoint,
    "-KokoroEndpoint", $KokoroEndpoint,
    "-KokoroRoot", $KokoroRoot,
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

$gateManifest = Get-ChildItem -Path (Join-Path $PSScriptRoot ".evavo\quality-results\release-gates") -Filter "release-gate.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $releaseStarted.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $gateManifest) {
    throw "Production quality gate passed but its release-gate.json could not be located for bundling."
}
$gateSource = $gateManifest.DirectoryName
$gateDestination = Join-Path $ReleaseRoot "gate"
Copy-Item -LiteralPath $gateSource -Destination $gateDestination -Recurse -Force

$heroOutputRoot = Join-Path $ReleaseRoot "hero"
$heroArgs = @(
    "-Python", $Python,
    "-ComfyEndpoint", $ComfyEndpoint,
    "-OutputRoot", $heroOutputRoot
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

$heroReview = Get-ChildItem -Path $heroOutputRoot -Filter "human_review.csv" -Recurse -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$kokoroReview = Get-ChildItem -Path $gateDestination -Filter "human_review.csv" -Recurse -File |
    Where-Object { $_.FullName -match '[\\/]kokoro[\\/]' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$releaseFinished = Get-Date
$summary = [ordered]@{
    schemaVersion = 1
    startedAt = $releaseStarted.ToString("o")
    finishedAt = $releaseFinished.ToString("o")
    durationSeconds = [math]::Round(($releaseFinished - $releaseStarted).TotalSeconds, 3)
    releaseRoot = $ReleaseRoot
    productionGateSource = $gateSource
    productionGate = (Join-Path $gateDestination "release-gate.json")
    heroReview = if ($heroReview) { $heroReview.FullName } else { $null }
    kokoroReview = if ($kokoroReview) { $kokoroReview.FullName } else { $null }
    endpoints = [ordered]@{
        comfy = $ComfyEndpoint
        kokoro = $KokoroEndpoint
        gateway = $GatewayEndpoint
        threeDWorker = $ThreeDWorkerEndpoint
    }
    roots = [ordered]@{
        comfy = $ComfyRoot
        kokoro = $KokoroRoot
        atmosphere = $AtmosphereRoot
        threeD = $ThreeDRoot
    }
    requireGateway = [bool]$RequireGateway
    require3DExecution = [bool]$Require3DExecution
    allowPartialImageRuntimeEvidence = [bool]$AllowPartialRuntimeEvidence
    automatedEvidencePassed = $true
    humanReviewRequired = $true
    automaticPromotion = $false
}
$summaryPath = Join-Path $ReleaseRoot "release-summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath -Encoding UTF8

Write-Host ""
Write-Host "Creating tamper-evident release manifest..." -ForegroundColor Cyan
& $Python .\release-evidence.py create --root $ReleaseRoot
if ($LASTEXITCODE -ne 0) {
    throw "Release evidence passed, but release-manifest creation failed."
}
$releaseManifest = Join-Path $ReleaseRoot "release-manifest.json"
& $Python .\release-evidence.py verify --manifest $releaseManifest
if ($LASTEXITCODE -ne 0) {
    throw "Release manifest was created but immediate integrity verification failed."
}

Write-Host ""
Write-Host "EVAVO full local generation release evidence completed." -ForegroundColor Green
Write-Host "Release root: $ReleaseRoot"
Write-Host "Integrity manifest: $releaseManifest"
if ($RequireGateway) {
    Write-Host "Gateway image round-trip proof: required and passed." -ForegroundColor Green
}
if ($Require3DExecution) {
    Write-Host "3D bounded execution-worker proof: required and passed." -ForegroundColor Green
}
Write-Host "Sibling runtime receipts were captured for Kokoro, 3D Studio and Atmosphere Studio."
if ($heroReview) { Write-Host "Image review sheet: $($heroReview.FullName)" }
if ($kokoroReview) { Write-Host "Kokoro review sheet: $($kokoroReview.FullName)" }
Write-Host "Final image-profile and voice promotion still require completing the human review sheets. No production default is changed automatically."
