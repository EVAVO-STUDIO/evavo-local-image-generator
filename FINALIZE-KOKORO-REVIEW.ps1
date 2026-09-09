param(
    [Parameter(Mandatory = $true)]
    [string]$ReviewCsv,
    [string]$Python = "python",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$args = @(".\kokoro-review-summary.py", "--review", $ReviewCsv)
if (-not [string]::IsNullOrWhiteSpace($Output)) {
    $args += @("--output", $Output)
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro listening review is incomplete or invalid. Complete every 1-5 score before finalizing."
}

Write-Host ""
Write-Host "Kokoro listening review summarized." -ForegroundColor Green
Write-Host "No production default voice was changed automatically. Use the evidence ranking with your listening judgment before changing EVAVO_KOKORO_VOICE."
