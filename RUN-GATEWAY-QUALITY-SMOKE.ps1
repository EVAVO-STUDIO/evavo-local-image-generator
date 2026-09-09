param(
    [string]$Python = "python",
    [string]$GatewayBase = "http://127.0.0.1:8000",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$Profile = "quality",
    [int]$Seed = 1337,
    [string]$Lora = "",
    [double]$LoraStrength = 0.7,
    [switch]$StartIfNeeded,
    [string]$Output = ".evavo\gateway\smoke-test-result.png"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

function Test-GatewayQualityContract {
    param([string]$Base)
    try {
        $payload = Invoke-RestMethod -Uri "$($Base.TrimEnd('/'))/capabilities" -Method Get -TimeoutSec 5 -ErrorAction Stop
        $profiles = @($payload.image.quality_profiles)
        $receipt = @($payload.image.reproducible_receipt)
        return (
            $payload.image.ready -eq $true -and
            $payload.image.per_request_quality -eq $true -and
            $payload.image.hero_two_pass -eq $true -and
            $payload.image.lora -eq $true -and
            $profiles -contains $Profile -and
            $receipt -contains "seed" -and
            $receipt -contains "workflow_sha256" -and
            $receipt -contains "quality_profile" -and
            $receipt -contains "output_width" -and
            $receipt -contains "output_height"
        )
    } catch {
        return $false
    }
}

Write-Host "EVAVO GATEWAY QUALITY SMOKE" -ForegroundColor Cyan
Write-Host "Gateway: $GatewayBase"
Write-Host "ComfyUI: $ComfyEndpoint"
Write-Host "Profile: $Profile"
Write-Host "Seed: $Seed"
if (-not [string]::IsNullOrWhiteSpace($Lora)) {
    Write-Host "LoRA: $Lora @ $LoraStrength"
}
Write-Host ""

if (-not (Test-GatewayQualityContract $GatewayBase)) {
    $healthReachable = $false
    try {
        $null = Invoke-RestMethod -Uri "$($GatewayBase.TrimEnd('/'))/health" -Method Get -TimeoutSec 4 -ErrorAction Stop
        $healthReachable = $true
    } catch {
        $healthReachable = $false
    }

    if ($healthReachable) {
        throw "A gateway is running at $GatewayBase but does not expose the current quality contract/profile. Restart it from current main before running this smoke test."
    }
    if (-not $StartIfNeeded) {
        throw "Gateway is not ready at $GatewayBase. Start it with .\START-EVAVO-QUALITY-STACK.ps1 -StartGateway or rerun this command with -StartIfNeeded."
    }

    $gatewayUri = [System.Uri]$GatewayBase
    if ($gatewayUri.Scheme -ne "http" -or $gatewayUri.Host -notin @("127.0.0.1", "localhost", "::1")) {
        throw "GatewayBase must be loopback HTTP."
    }
    $comfyUri = [System.Uri]$ComfyEndpoint
    if ($comfyUri.Scheme -ne "http" -or $comfyUri.Host -notin @("127.0.0.1", "localhost", "::1")) {
        throw "ComfyEndpoint must be loopback HTTP."
    }

    $env:COMFYUI_ENDPOINT = $ComfyEndpoint.TrimEnd('/')
    $env:EVAVO_COMFYUI_ENDPOINT = $ComfyEndpoint.TrimEnd('/')
    $env:EVAVO_GATEWAY_HOST = "127.0.0.1"
    $env:EVAVO_GATEWAY_PORT = "$($gatewayUri.Port)"

    & .\START-GATEWAY.ps1 -SkipInstall -SkipValidation
    if ($LASTEXITCODE -ne 0) {
        throw "Gateway startup failed."
    }

    $deadline = (Get-Date).AddSeconds(120)
    do {
        if (Test-GatewayQualityContract $GatewayBase) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if (-not (Test-GatewayQualityContract $GatewayBase)) {
        throw "Gateway started but did not expose the required quality contract within 120 seconds."
    }
}

$outputPath = if ([System.IO.Path]::IsPathRooted($Output)) {
    [System.IO.Path]::GetFullPath($Output)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Output))
}
$outputParent = Split-Path -Parent $outputPath
if ($outputParent) {
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}

$args = @(
    ".\gateway-smoke-test.py",
    "--base", $GatewayBase,
    "--profile", $Profile,
    "--seed", "$Seed",
    "--output", $outputPath
)
if (-not [string]::IsNullOrWhiteSpace($Lora)) {
    $args += @("--lora", $Lora, "--lora-strength", "$LoraStrength")
}

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "Gateway image-quality smoke failed. Inspect the JSON output above and the gateway/service logs."
}

Write-Host ""
Write-Host "Gateway image-quality boundary passed." -ForegroundColor Green
Write-Host "Artifact: $outputPath"
