param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [string]$Python = "python",
    [string]$ImageBaseline = "quality"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$release = [System.IO.Path]::GetFullPath($ReleaseRoot)
if (-not (Test-Path -LiteralPath $release -PathType Container)) {
    throw "Release root not found: $release"
}

$imageReview = Get-ChildItem -Path (Join-Path $release "hero") -Filter "human_review.csv" -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $imageReview) {
    throw "Image human_review.csv was not found under $release\hero"
}

$kokoroReview = Get-ChildItem -Path (Join-Path $release "gate") -Filter "human_review.csv" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '[\\/]kokoro[\\/]' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $kokoroReview) {
    throw "Kokoro human_review.csv was not found under $release\gate"
}

Write-Host "Finalizing image human review..." -ForegroundColor Cyan
& .\FINALIZE-QUALITY-REVIEW.ps1 -Review $imageReview.FullName -Baseline $ImageBaseline -Python $Python
if ($LASTEXITCODE -ne 0) { throw "Image human review finalization failed." }

Write-Host "Finalizing Kokoro listening review..." -ForegroundColor Cyan
& .\FINALIZE-KOKORO-REVIEW.ps1 -ReviewCsv $kokoroReview.FullName -Python $Python
if ($LASTEXITCODE -ne 0) { throw "Kokoro human review finalization failed." }

$imageSummary = Join-Path $imageReview.DirectoryName "human_review_summary.json"
$kokoroSummary = Join-Path $kokoroReview.DirectoryName "review-summary.json"
if (-not (Test-Path -LiteralPath $imageSummary -PathType Leaf)) {
    throw "Image review summary was not produced: $imageSummary"
}
if (-not (Test-Path -LiteralPath $kokoroSummary -PathType Leaf)) {
    throw "Kokoro review summary was not produced: $kokoroSummary"
}

$finalization = [ordered]@{
    schemaVersion = 1
    finalizedAt = (Get-Date).ToString("o")
    releaseRoot = $release
    imageReview = [ordered]@{
        csv = $imageReview.FullName
        csvSha256 = (Get-FileHash -LiteralPath $imageReview.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        summary = $imageSummary
        summarySha256 = (Get-FileHash -LiteralPath $imageSummary -Algorithm SHA256).Hash.ToLowerInvariant()
        baseline = $ImageBaseline
    }
    kokoroReview = [ordered]@{
        csv = $kokoroReview.FullName
        csvSha256 = (Get-FileHash -LiteralPath $kokoroReview.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        summary = $kokoroSummary
        summarySha256 = (Get-FileHash -LiteralPath $kokoroSummary -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    humanReviewComplete = $true
    automaticPromotion = $false
    note = "Human review evidence is complete. Profile/voice promotion remains an explicit operator decision."
}
$finalizationPath = Join-Path $release "finalization.json"
$finalization | ConvertTo-Json -Depth 6 | Set-Content -Path $finalizationPath -Encoding UTF8

Write-Host "Resealing full release evidence after human review..." -ForegroundColor Cyan
& $Python .\release-evidence.py create --root $release
if ($LASTEXITCODE -ne 0) { throw "Could not create final release integrity manifest." }
$manifest = Join-Path $release "release-manifest.json"
& $Python .\release-evidence.py verify --manifest $manifest
if ($LASTEXITCODE -ne 0) { throw "Final release integrity verification failed after resealing." }

Write-Host ""
Write-Host "Full release human review finalized and integrity seal refreshed." -ForegroundColor Green
Write-Host "Finalization receipt: $finalizationPath"
Write-Host "Integrity manifest: $manifest"
Write-Host "No image profile or voice default was changed automatically."
