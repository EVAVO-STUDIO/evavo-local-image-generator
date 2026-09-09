param(
    [Parameter(Mandatory = $true)]
    [string]$Review,
    [string]$Baseline = "quality",
    [string]$Python = "python",
    [switch]$AllowIncomplete
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$reviewPath = [System.IO.Path]::GetFullPath($Review)
if (-not (Test-Path -LiteralPath $reviewPath -PathType Leaf)) {
    throw "Human review CSV not found: $reviewPath"
}

$args = @(
    ".\quality-review-summary.py",
    "--review", $reviewPath,
    "--baseline", $Baseline
)
if ($AllowIncomplete) {
    $args += "--allow-incomplete"
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "Human quality review is incomplete or invalid. Complete every 1-5 score before treating the comparison as release evidence."
}

$summary = Join-Path (Split-Path -Parent $reviewPath) "human_review_summary.json"
Write-Host ""
Write-Host "Human review evidence summarized." -ForegroundColor Green
Write-Host "Summary: $summary"
Write-Host "No production default was changed automatically. Use the paired human-score evidence plus artifact review and measured runtime cost to make the promotion decision."
