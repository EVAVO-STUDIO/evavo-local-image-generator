param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$Checkpoint = "",
    [string]$Prompts = "product,portrait,landscape,interior,game_art",
    [string]$Seeds = "1337,424242",
    [string]$OutputRoot = ".evavo\quality-results\hero-release",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO HERO QUALITY RELEASE CHECK" -ForegroundColor Cyan
Write-Host "ComfyUI: $ComfyEndpoint"
Write-Host "Profiles: quality,hero,detail,euler_reference,legacy_768_reference"
Write-Host "Prompts: $Prompts"
Write-Host "Seeds: $Seeds"
Write-Host ""

& $Python .\test_quality_profiles.py
if ($LASTEXITCODE -ne 0) {
    throw "Offline quality-profile regressions failed. Hero rendering was not started."
}

$resolvedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
$startedAt = Get-Date

$args = @(
    ".\quality-benchmark.py",
    "--endpoint", $ComfyEndpoint,
    "--profiles", "quality,hero,detail,euler_reference,legacy_768_reference",
    "--prompts", $Prompts,
    "--seeds", $Seeds,
    "--output", $resolvedOutputRoot
)
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $args += @("--checkpoint", $Checkpoint)
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "Hero A/B benchmark failed. Review the generated manifest before promotion."
}

$manifest = Get-ChildItem -Path $resolvedOutputRoot -Filter "manifest.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $manifest) {
    throw "Hero benchmark completed but no new manifest.json was found under $resolvedOutputRoot"
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

# The parallel 8189 runtime deliberately shares model bytes with the working
# ComfyUI install. Use the migration receipt so attestation hashes the real
# source checkpoint/LoRA rather than incorrectly looking only inside -next.
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

Write-Host ""
Write-Host "Capturing runtime and model-byte evidence..." -ForegroundColor Cyan
& $Python @runtimeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Hero images rendered, but runtime/model attestation is incomplete. Use -AllowPartialRuntimeEvidence only for exploratory comparisons, not release evidence."
}

Write-Host ""
Write-Host "Building technical diagnostics and human-review report..." -ForegroundColor Cyan
& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "Hero benchmark images rendered, but quality-report generation failed. Review $($manifest.FullName)."
}

$report = Join-Path $manifest.DirectoryName "report.html"
$review = Join-Path $manifest.DirectoryName "human_review.csv"
$runtime = Join-Path $manifest.DirectoryName "runtime-evidence.json"
Write-Host ""
Write-Host "Hero A/B benchmark and review package completed successfully." -ForegroundColor Green
Write-Host "Report: $report"
Write-Host "Human review: $review"
Write-Host "Runtime evidence: $runtime"
Write-Host "Do not make hero the universal default from timings or technical metrics alone; review the fixed-seed images at fit-to-screen and 100% zoom, then complete the human review sheet."
