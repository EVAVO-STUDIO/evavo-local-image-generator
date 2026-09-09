param(
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$Checkpoint = "",
    [string]$Prompts = "product,portrait,landscape,interior,game_art",
    [string]$Seeds = "1337,424242",
    [string]$OutputRoot = ".evavo\quality-results\hero-release"
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

Write-Host ""
Write-Host "Building technical diagnostics and human-review report..." -ForegroundColor Cyan
& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "Hero benchmark images rendered, but quality-report generation failed. Review $($manifest.FullName)."
}

$report = Join-Path $manifest.DirectoryName "report.html"
$review = Join-Path $manifest.DirectoryName "human_review.csv"
Write-Host ""
Write-Host "Hero A/B benchmark and review package completed successfully." -ForegroundColor Green
Write-Host "Report: $report"
Write-Host "Human review: $review"
Write-Host "Do not make hero the universal default from timings or technical metrics alone; review the fixed-seed images at fit-to-screen and 100% zoom, then complete the human review sheet."
