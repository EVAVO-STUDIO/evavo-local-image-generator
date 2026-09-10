param(
    [Parameter(Mandatory = $true)]
    [string]$Vaes,
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "",
    [string]$Checkpoint = "",
    [string]$Profile = "quality",
    [string]$Prompts = "product,portrait,landscape,interior",
    [string]$Seeds = "1337",
    [string]$OutputRoot = ".evavo\quality-results\vae-sweeps",
    [switch]$AllowPartialRuntimeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO VAE QUALITY SWEEP" -ForegroundColor Cyan
Write-Host "ComfyUI: $ComfyEndpoint"
Write-Host "VAEs: baked checkpoint VAE + $Vaes"
Write-Host "Sampling profile: $Profile"
Write-Host "Prompts: $Prompts"
Write-Host "Seeds: $Seeds"
Write-Host ""

& $Python .\test_vae_quality.py
if ($LASTEXITCODE -ne 0) {
    throw "Offline VAE graph regressions failed. No VAE renders were started."
}

$resolvedOutputRoot = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
}
New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
$startedAt = Get-Date

$args = @(
    ".\vae-sweep.py",
    "--vaes", $Vaes,
    "--endpoint", $ComfyEndpoint,
    "--profile", $Profile,
    "--prompts", $Prompts,
    "--seeds", $Seeds,
    "--output", $resolvedOutputRoot
)
if (-not [string]::IsNullOrWhiteSpace($Checkpoint)) {
    $args += @("--checkpoint", $Checkpoint)
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "VAE sweep failed. Inspect the newest manifest under $resolvedOutputRoot."
}

$manifest = Get-ChildItem -Path $resolvedOutputRoot -Filter "manifest.json" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $manifest) {
    throw "VAE sweep completed but no new manifest.json was found."
}

& $Python .\quality-report.py --manifest $manifest.FullName
if ($LASTEXITCODE -ne 0) {
    throw "VAE renders completed, but quality-report generation failed."
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
            $runtimeArgs += @("--model-root", (Join-Path $currentRoot "models\vae"))
            $runtimeArgs += @("--model-root", (Join-Path $currentRoot "models\vae_approx"))
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
    throw "VAE images rendered, but VAE/checkpoint/runtime attestation is incomplete."
}

Write-Host ""
Write-Host "VAE quality comparison completed." -ForegroundColor Green
Write-Host "Manifest: $($manifest.FullName)"
Write-Host "Report: $(Join-Path $manifest.DirectoryName 'report.html')"
Write-Host "Human review: $(Join-Path $manifest.DirectoryName 'human_review.csv')"
Write-Host "Runtime/model evidence: $(Join-Path $manifest.DirectoryName 'runtime-evidence.json')"
Write-Host "The baked checkpoint VAE remains the production default until the fixed-seed human review proves an external decoder is better."
