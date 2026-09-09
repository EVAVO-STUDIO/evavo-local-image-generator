param(
    [Parameter(Mandatory = $true)]
    [string]$Checkpoint,
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
    [string]$ReleaseRoot = "",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$maskedKeys = @(
    "EVAVO_IMAGE_QUALITY_PROFILE",
    "EVAVO_IMAGE_WIDTH",
    "EVAVO_IMAGE_HEIGHT",
    "EVAVO_IMAGE_STEPS",
    "EVAVO_IMAGE_CFG",
    "EVAVO_IMAGE_SAMPLER",
    "EVAVO_IMAGE_SCHEDULER",
    "EVAVO_IMAGE_DENOISE",
    "EVAVO_IMAGE_UPSCALE_FACTOR",
    "EVAVO_IMAGE_SECOND_STEPS",
    "EVAVO_IMAGE_SECOND_CFG",
    "EVAVO_IMAGE_SECOND_SAMPLER",
    "EVAVO_IMAGE_SECOND_SCHEDULER",
    "EVAVO_IMAGE_SECOND_DENOISE",
    "EVAVO_IMAGE_LATENT_UPSCALE_METHOD",
    "EVAVO_IMAGE_LORA",
    "EVAVO_IMAGE_LORA_MODEL_STRENGTH",
    "EVAVO_IMAGE_LORA_CLIP_STRENGTH",
    "EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS",
    "EVAVO_COMFYUI_WORKFLOW"
)

$previous = @{}
foreach ($key in $maskedKeys) {
    $value = [Environment]::GetEnvironmentVariable($key, "Process")
    if ($null -ne $value) {
        $previous[$key] = $value
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($ReleaseRoot)) {
    $ReleaseRoot = Join-Path $PSScriptRoot ".evavo\quality-results\full-release\$stamp"
} elseif ([System.IO.Path]::IsPathRooted($ReleaseRoot)) {
    $ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
} else {
    $ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $ReleaseRoot))
}

Write-Host "EVAVO CANONICAL FROZEN RELEASE" -ForegroundColor Cyan
Write-Host "Checkpoint: $Checkpoint"
Write-Host "Release root: $ReleaseRoot"
Write-Host "Ambient EVAVO_IMAGE_* / EVAVO_COMFYUI_WORKFLOW values will not influence the controlled release run."
Write-Host ""

$releaseSucceeded = $false
try {
    foreach ($key in $maskedKeys) {
        [Environment]::SetEnvironmentVariable($key, $null, "Process")
    }

    $args = @(
        "-Python", $Python,
        "-ComfyEndpoint", $ComfyEndpoint,
        "-KokoroEndpoint", $KokoroEndpoint,
        "-KokoroRoot", $KokoroRoot,
        "-GatewayEndpoint", $GatewayEndpoint,
        "-AtmosphereRoot", $AtmosphereRoot,
        "-ThreeDRoot", $ThreeDRoot,
        "-ThreeDWorkerEndpoint", $ThreeDWorkerEndpoint,
        "-Checkpoint", $Checkpoint,
        "-ReleaseRoot", $ReleaseRoot
    )
    if (-not [string]::IsNullOrWhiteSpace($ComfyRoot)) {
        $args += @("-ComfyRoot", $ComfyRoot)
    }
    if ($RequireGateway) { $args += "-RequireGateway" }
    if ($Require3DExecution) { $args += "-Require3DExecution" }
    if ($AllowPartialRuntimeEvidence) { $args += "-AllowPartialRuntimeEvidence" }

    & .\RUN-FULL-QUALITY-RELEASE.ps1 @args
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen full release failed."
    }
    $releaseSucceeded = $true
}
finally {
    foreach ($key in $maskedKeys) {
        [Environment]::SetEnvironmentVariable($key, $null, "Process")
    }
    foreach ($entry in $previous.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, "Process")
    }
}

if (-not $releaseSucceeded) {
    throw "Frozen release did not complete successfully."
}

$policy = [ordered]@{
    schemaVersion = 1
    recordedAt = (Get-Date).ToString("o")
    authority = "release evidence only; no automatic quality/profile/voice promotion"
    imageEnvironmentPolicy = [ordered]@{
        frozen = $true
        maskedKeys = $maskedKeys
        keysPresentBeforeRun = @($previous.Keys | Sort-Object)
        environmentValuesRecorded = $false
        reason = "Controlled A/B and release evidence must not inherit ambient image recipe or workflow overrides."
    }
    checkpoint = $Checkpoint
    checkpointRequestedExplicitly = $true
    comfyEndpoint = $ComfyEndpoint
    requireGateway = [bool]$RequireGateway
    require3DExecution = [bool]$Require3DExecution
}
$policyPath = Join-Path $ReleaseRoot "release-policy.json"
$policy | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $policyPath -Encoding UTF8

# RUN-FULL-QUALITY-RELEASE seals its evidence before this wrapper adds the
# environment policy. Reseal immediately so the canonical release bundle is
# internally complete and tamper-evident.
& $Python .\release-evidence.py create --root $ReleaseRoot
if ($LASTEXITCODE -ne 0) {
    throw "Frozen release completed, but evidence resealing failed after release-policy.json was added."
}
$manifest = Join-Path $ReleaseRoot "release-manifest.json"
& $Python .\release-evidence.py verify --manifest $manifest
if ($LASTEXITCODE -ne 0) {
    throw "Frozen release evidence failed immediate integrity verification."
}

Write-Host ""
Write-Host "Canonical frozen release evidence passed and was sealed." -ForegroundColor Green
Write-Host "Release: $ReleaseRoot"
Write-Host "Policy: $policyPath"
Write-Host "Manifest: $manifest"
Write-Host "After completing both human review sheets, run:"
Write-Host "  .\FINALIZE-FULL-RELEASE.ps1 -ReleaseRoot `"$ReleaseRoot`""
