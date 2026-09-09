param(
    [ValidateSet("quick", "standard", "full")]
    [string]$Mode = "standard",
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [switch]$SkipComfy,
    [switch]$SkipKokoro,
    [switch]$SkipAtmosphere
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$Failures = New-Object System.Collections.Generic.List[string]
$Started = Get-Date
$ResultRoot = Join-Path $PSScriptRoot ".evavo\quality-results\release-gates\$($Started.ToString('yyyyMMdd-HHmmss'))"
New-Item -ItemType Directory -Force -Path $ResultRoot | Out-Null

function Invoke-Gate {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    $safe = ($Name -replace '[^A-Za-z0-9._-]', '-')
    $LogPath = Join-Path $ResultRoot "$safe.log"
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments 2>&1 | Tee-Object -FilePath $LogPath
        $code = $LASTEXITCODE
    } catch {
        $_ | Out-String | Add-Content -Path $LogPath
        $code = 1
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        $Failures.Add("$Name (exit $code)")
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        return $false
    }
    Write-Host "[PASS] $Name" -ForegroundColor Green
    return $true
}

# Offline gates first: fast and deterministic, no GPU/service dependency.
Invoke-Gate "image-quality-profile-tests" $PSScriptRoot $Python @("test_quality_profiles.py") | Out-Null

if (-not $SkipComfy) {
    $profiles = "quality,euler_reference"
    $prompts = "product,portrait"
    $seeds = "1337"
    if ($Mode -eq "standard") {
        $profiles = "quality,euler_reference,legacy_768_reference"
        $prompts = "product,portrait,landscape,interior"
    } elseif ($Mode -eq "full") {
        $profiles = "quality,detail,euler_reference,legacy_768_reference"
        $prompts = "product,portrait,landscape,interior,game_art"
        $seeds = "1337,424242"
    }
    Invoke-Gate "comfyui-fixed-seed-quality" $PSScriptRoot $Python @(
        "quality-benchmark.py",
        "--endpoint", $ComfyEndpoint,
        "--profiles", $profiles,
        "--prompts", $prompts,
        "--seeds", $seeds,
        "--output", (Join-Path $ResultRoot "comfyui")
    ) | Out-Null
}

if (-not $SkipKokoro) {
    $texts = "neutral"
    if ($Mode -eq "standard") { $texts = "neutral,numbers" }
    if ($Mode -eq "full") { $texts = "neutral,numbers,expressive" }
    Invoke-Gate "kokoro-golden-audio" $PSScriptRoot $Python @(
        "kokoro-quality-test.py",
        "--endpoint", $KokoroEndpoint,
        "--texts", $texts,
        "--output", (Join-Path $ResultRoot "kokoro")
    ) | Out-Null
}

if (-not $SkipAtmosphere) {
    if (-not (Test-Path (Join-Path $AtmosphereRoot "package.json"))) {
        $Failures.Add("Atmosphere Studio not found at $AtmosphereRoot")
        Write-Host "[FAIL] Atmosphere Studio not found at $AtmosphereRoot" -ForegroundColor Red
    } else {
        $npm = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { "npm.cmd" } else { "npm" }
        Invoke-Gate "atmosphere-doctor" $AtmosphereRoot $npm @("run", "doctor") | Out-Null
        if ($Mode -in @("standard", "full")) {
            Invoke-Gate "atmosphere-media-smoke" $AtmosphereRoot $npm @("run", "smoke:media") | Out-Null
            Invoke-Gate "atmosphere-typecheck" $AtmosphereRoot $npm @("run", "typecheck") | Out-Null
        }
        if ($Mode -eq "full") {
            Invoke-Gate "atmosphere-production-safety" $AtmosphereRoot $npm @("run", "safety:production") | Out-Null
            Invoke-Gate "atmosphere-production-tests" $AtmosphereRoot $npm @("run", "test:production") | Out-Null
            Invoke-Gate "atmosphere-build" $AtmosphereRoot $npm @("run", "build") | Out-Null
        }
    }
}

$Finished = Get-Date
$Summary = [ordered]@{
    schemaVersion = 1
    mode = $Mode
    startedAt = $Started.ToString("o")
    finishedAt = $Finished.ToString("o")
    durationSeconds = [math]::Round(($Finished - $Started).TotalSeconds, 3)
    comfyEndpoint = $ComfyEndpoint
    kokoroEndpoint = $KokoroEndpoint
    atmosphereRoot = $AtmosphereRoot
    resultRoot = $ResultRoot
    ok = ($Failures.Count -eq 0)
    failures = @($Failures)
}
$Summary | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $ResultRoot "release-gate.json") -Encoding UTF8

Write-Host ""
Write-Host "Results: $ResultRoot"
if ($Failures.Count -gt 0) {
    Write-Host "PRODUCTION QUALITY GATE FAILED" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "PRODUCTION QUALITY GATE PASSED" -ForegroundColor Green
exit 0
