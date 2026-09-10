param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$Checkpoint = "",
    [string]$Profiles = "quality,hero,detail,euler_reference",
    [string]$PromptId = "product",
    [int]$Seed = 1337,
    [ValidateRange(1,20)]
    [int]$Repeats = 3,
    [ValidateRange(0,5)]
    [int]$Warmup = 1,
    [ValidateRange(0,16)]
    [int]$GpuIndex = 0,
    [string]$OutputRoot = ".evavo\quality-results\gpu-benchmarks",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO GPU QUALITY BENCHMARK" -ForegroundColor Cyan
Write-Host "ComfyUI: $ComfyEndpoint"
Write-Host "Profiles: $Profiles"
Write-Host "Prompt: $PromptId"
Write-Host "Seed: $Seed"
Write-Host "Repeats: $Repeats (+ $Warmup warmup)"
Write-Host "GPU index: $GpuIndex"
Write-Host ""

& $Python .\test_gpu_quality_benchmark.py
if ($LASTEXITCODE -ne 0) {
    throw "Offline GPU-benchmark regressions failed. No benchmark renders were started."
}

$resolvedOutputRoot = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
}
New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
$startedAt = Get-Date

$args = @(
    ".\gpu-quality-benchmark.py",
    "--endpoint", $ComfyEndpoint,
    "--profiles", $Profiles,
    "--prompt-id", $PromptId,
    "--seed", "$Seed",
    "--repeats", "$Repeats",
    "--warmup", "$Warmup",
    "--gpu-index", "$GpuIndex",
    "--output", $resolvedOutputRoot
)
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $args += @("--checkpoint", $Checkpoint)
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "GPU quality benchmark failed. Inspect the newest manifest under $resolvedOutputRoot."
}

$manifest = Get-ChildItem -Path $resolvedOutputRoot -Filter "manifest.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $manifest) {
    throw "GPU benchmark completed but no new manifest.json was found."
}

Write-Host ""
Write-Host "Building side-by-side image diagnostics..." -ForegroundColor Cyan
& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "GPU benchmark rendered successfully, but quality-report generation failed."
}

if ([string]::IsNullOrWhiteSpace($ComfyRoot)) {
    $uri = [System.Uri]$ComfyEndpoint
    $ComfyRoot = if ($uri.Port -eq 8189) { "C:\AI\ComfyUI-next" } else { "C:\AI\ComfyUI" }
}
$ComfyRoot = [System.IO.Path]::GetFullPath($ComfyRoot)
$runtimeArgs = @(
    ".\runtime-snapshot.py",
    "--manifest", $manifest.FullName,
    "--endpoint", $ComfyEndpoint,
    "--comfy-root", $ComfyRoot,
    "--output", (Join-Path $manifest.DirectoryName "runtime-evidence.json")
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
        Write-Warning "Could not read ComfyUI-next runtime receipt; runtime evidence may be partial."
    }
}
if (-not $AllowPartialRuntimeEvidence) {
    $runtimeArgs += "--require-complete"
}

& $Python @runtimeArgs
if ($LASTEXITCODE -ne 0) {
    throw "GPU benchmark completed but runtime/model attestation is incomplete."
}

Write-Host ""
Write-Host "GPU quality benchmark evidence completed." -ForegroundColor Green
Write-Host "Manifest: $($manifest.FullName)"
Write-Host "Report: $(Join-Path $manifest.DirectoryName 'report.html')"
Write-Host "Human review: $(Join-Path $manifest.DirectoryName 'human_review.csv')"
Write-Host "Runtime evidence: $(Join-Path $manifest.DirectoryName 'runtime-evidence.json')"
Write-Host "Use measured time/VRAM cost together with the side-by-side human review. Performance evidence alone never promotes a profile."
