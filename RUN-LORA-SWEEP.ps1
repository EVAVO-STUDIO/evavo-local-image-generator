param(
    [Parameter(Mandatory = $true)]
    [string]$Lora,
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$Negative = "",
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$Checkpoint = "",
    [string]$Profile = "quality",
    [int]$Seed = 1337,
    [string]$Strengths = "0,0.5,0.7,0.9",
    [string]$OutputRoot = ".evavo\quality-results\lora-sweeps"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO LORA QUALITY SWEEP" -ForegroundColor Cyan
Write-Host "LoRA: $Lora"
Write-Host "Profile: $Profile"
Write-Host "Seed: $Seed"
Write-Host "Strengths: $Strengths"
Write-Host ""

& $Python .\test_quality_profiles.py
if ($LASTEXITCODE -ne 0) {
    throw "Offline quality/LoRA regressions failed. Sweep was not started."
}

$resolvedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
$startedAt = Get-Date

$args = @(
    ".\lora-sweep.py",
    "--lora", $Lora,
    "--prompt", $Prompt,
    "--negative", $Negative,
    "--endpoint", $ComfyEndpoint,
    "--profile", $Profile,
    "--seed", "$Seed",
    "--strengths", $Strengths,
    "--output", $resolvedOutputRoot
)
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $args += @("--checkpoint", $Checkpoint)
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "LoRA strength sweep failed. Review the newest manifest under $resolvedOutputRoot."
}

$manifest = Get-ChildItem -Path $resolvedOutputRoot -Filter "manifest.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $manifest) {
    throw "LoRA sweep completed but no new manifest.json was found under $resolvedOutputRoot"
}

& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "LoRA images rendered, but the side-by-side review report failed."
}

Write-Host ""
Write-Host "LoRA A/B review package completed." -ForegroundColor Green
Write-Host "Report: $(Join-Path $manifest.DirectoryName 'report.html')"
Write-Host "Review sheet: $(Join-Path $manifest.DirectoryName 'human_review.csv')"
Write-Host "Use the lowest strength that reliably adds the intended identity/style/detail without increasing artifacts or overpowering the base checkpoint."
