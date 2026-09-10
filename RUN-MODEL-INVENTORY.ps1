param(
    [string]$Python = "python",
    [string]$ComfyRoot = "C:\AI\ComfyUI",
    [string]$NextComfyRoot = "C:\AI\ComfyUI-next",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$Output = ".evavo\model-inventory.json",
    [switch]$HashModels,
    [switch]$SkipLiveComfy
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

& $Python .\test_model_inventory.py
if ($LASTEXITCODE -ne 0) {
    throw "Offline model-inventory regressions failed."
}

$outputPath = if ([System.IO.Path]::IsPathRooted($Output)) {
    [System.IO.Path]::GetFullPath($Output)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Output))
}

$args = @(".\model-inventory.py", "--endpoint", $ComfyEndpoint, "--output", $outputPath)
foreach ($root in @($ComfyRoot, $NextComfyRoot)) {
    $modelRoot = Join-Path $root "models"
    if (Test-Path -LiteralPath $modelRoot -PathType Container) {
        $args += @("--root", $modelRoot)
    }
}
if ($HashModels) {
    $args += "--hash"
}
if ($SkipLiveComfy) {
    $args += "--no-live"
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "Model inventory failed."
}

Write-Host ""
Write-Host "Model inventory completed." -ForegroundColor Green
Write-Host "Inventory: $outputPath"
if (-not $HashModels) {
    Write-Host "Full model hashes were skipped to avoid re-reading multi-GB weights. Use -HashModels when exact duplicate/provenance evidence is needed."
}
