param(
    [Parameter(Mandatory = $true)]
    [string]$Checkpoint,
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$Profiles = "quality,hero,detail",
    [string]$Prompt = "product",
    [int]$Seed = 1337,
    [ValidateRange(1, 20)]
    [int]$Repeats = 3,
    [ValidateRange(0, 5)]
    [int]$Warmup = 1,
    [ValidateRange(0, 31)]
    [int]$GpuIndex = 0,
    [ValidateRange(0.1, 5.0)]
    [double]$TelemetryInterval = 0.25,
    [string]$OutputRoot = ".evavo\quality-results\performance",
    [switch]$RequireGpuTelemetry,
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
}
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$started = Get-Date

Write-Host "EVAVO CONTROLLED GPU PERFORMANCE BENCHMARK" -ForegroundColor Cyan
Write-Host "ComfyUI: $ComfyEndpoint"
Write-Host "Checkpoint: $Checkpoint"
Write-Host "Profiles: $Profiles"
Write-Host "Prompt: $Prompt"
Write-Host "Seed: $Seed"
Write-Host "Repeats: $Repeats"
Write-Host "Warmup: $Warmup"
Write-Host "GPU index: $GpuIndex"
Write-Host ""

& $Python .\test_frozen_quality_environment.py
if ($LASTEXITCODE -ne 0) {
    throw "Frozen image-recipe regressions failed. Performance benchmark was not started."
}

$args = @(
    ".\gpu-performance-benchmark.py",
    "--endpoint", $ComfyEndpoint,
    "--checkpoint", $Checkpoint,
    "--profiles", $Profiles,
    "--prompt", $Prompt,
    "--seed", "$Seed",
    "--repeats", "$Repeats",
    "--warmup", "$Warmup",
    "--gpu-index", "$GpuIndex",
    "--telemetry-interval", "$TelemetryInterval",
    "--output", $resolvedOutput
)
if ($RequireGpuTelemetry) { $args += "--require-gpu-telemetry" }

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "GPU performance benchmark failed. Review the newest performance.json under $resolvedOutput."
}

$performance = Get-ChildItem -Path $resolvedOutput -Filter "performance.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $performance) {
    throw "Performance benchmark completed but no new performance.json was found under $resolvedOutput"
}

if ([string]::IsNullOrWhiteSpace($ComfyRoot)) {
    $uri = [System.Uri]$ComfyEndpoint
    $ComfyRoot = if ($uri.Port -eq 8189) { "C:\AI\ComfyUI-next" } else { "C:\AI\ComfyUI" }
}
$ComfyRoot = [System.IO.Path]::GetFullPath($ComfyRoot)
$runtimeEvidence = Join-Path $performance.DirectoryName "runtime-evidence.json"
$runtimeArgs = @(
    ".\runtime-snapshot.py",
    "--manifest", $performance.FullName,
    "--endpoint", $ComfyEndpoint,
    "--comfy-root", $ComfyRoot,
    "--output", $runtimeEvidence
)

$nextReceipt = Join-Path $ComfyRoot "evavo-next-runtime.json"
if (Test-Path -LiteralPath $nextReceipt -PathType Leaf) {
    try {
        $nextInfo = Get-Content -LiteralPath $nextReceipt -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($nextInfo.currentRoot) {
            $currentRoot = [System.IO.Path]::GetFullPath([string]$nextInfo.currentRoot)
            $runtimeArgs += @("--model-root", (Join-Path $currentRoot "models\checkpoints"))
            $runtimeArgs += @("--model-root", (Join-Path $currentRoot "models\loras"))
        }
    } catch {
        if (-not $AllowPartialRuntimeEvidence) {
            throw "Could not read ComfyUI-next runtime receipt $nextReceipt: $($_.Exception.Message)"
        }
        Write-Warning "Could not read ComfyUI-next runtime receipt; performance runtime evidence may be partial."
    }
}
if (-not $AllowPartialRuntimeEvidence) { $runtimeArgs += "--require-complete" }

Write-Host ""
Write-Host "Capturing runtime/model attestation outside the timed render loop..." -ForegroundColor Cyan
& $Python @runtimeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Render timings completed, but runtime/model attestation failed."
}

Write-Host ""
Write-Host "Controlled GPU performance evidence completed." -ForegroundColor Green
Write-Host "Performance: $($performance.FullName)"
Write-Host "Runtime evidence: $runtimeEvidence"
Write-Host "No image profile, sampler or concurrency default was changed."
