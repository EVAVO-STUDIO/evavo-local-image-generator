param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$release = [System.IO.Path]::GetFullPath($ReleaseRoot)
$manifest = Join-Path $release "release-manifest.json"
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw "Release integrity manifest not found: $manifest"
}

& $Python .\release-evidence.py verify --manifest $manifest
if ($LASTEXITCODE -ne 0) {
    throw "Release evidence integrity check failed. Do not treat this bundle as unchanged release evidence."
}
Write-Host "Release evidence integrity verified: $release" -ForegroundColor Green
