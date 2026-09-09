param(
    [Parameter(Mandatory = $true)]
    [string]$Lora,
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$Negative = "",
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$Checkpoint = "",
    [string]$Profile = "quality",
    [int]$Seed = 1337,
    [string]$Strengths = "0,0.5,0.7,0.9",
    [string]$OutputRoot = ".evavo\quality-results\lora-sweeps",
    [switch]$AllowPartialRuntimeEvidence
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

$resolvedOutputRoot = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
}
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
    throw "LoRA images rendered, but checkpoint/LoRA/runtime attestation is incomplete. Use -AllowPartialRuntimeEvidence only for exploratory sweeps."
}

& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "LoRA images rendered, but the side-by-side review report failed."
}

Write-Host ""
Write-Host "LoRA A/B review package completed." -ForegroundColor Green
Write-Host "Report: $(Join-Path $manifest.DirectoryName 'report.html')"
Write-Host "Review sheet: $(Join-Path $manifest.DirectoryName 'human_review.csv')"
Write-Host "Runtime evidence: $(Join-Path $manifest.DirectoryName 'runtime-evidence.json')"
Write-Host "Use the lowest strength that reliably adds the intended identity/style/detail without increasing artifacts or overpowering the base checkpoint."
