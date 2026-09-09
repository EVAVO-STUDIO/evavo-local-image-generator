param(
    [ValidateSet("quick", "standard", "full")]
    [string]$Mode = "standard",
    [string]$Python = "python",
    [string]$ComfyEndpoint = "http://127.0.0.1:8188",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$KokoroRoot = "C:\AI\Kokoro-FastAPI",
    [string]$GatewayEndpoint = "http://127.0.0.1:8000",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [string]$ThreeDRoot = "C:\GitRepos\evavo-3d-studio",
    [string]$ThreeDWorkerEndpoint = "http://127.0.0.1:4314",
    [switch]$RequireGateway,
    [switch]$Require3DExecution,
    [switch]$SkipComfy,
    [switch]$SkipKokoro,
    [switch]$SkipAtmosphere,
    [switch]$Skip3D
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

$Failures = New-Object System.Collections.Generic.List[string]
$Started = Get-Date
$ResultRoot = Join-Path $PSScriptRoot ".evavo\quality-results\release-gates\$($Started.ToString('yyyyMMdd-HHmmss'))"
New-Item -ItemType Directory -Force -Path $ResultRoot | Out-Null
$KokoroRuntimeEvidence = Join-Path $ResultRoot "kokoro-runtime.json"
$ThreeDRuntimeEvidence = Join-Path $ResultRoot "3d-runtime.json"
$AtmosphereRuntimeEvidence = Join-Path $ResultRoot "atmosphere-runtime.json"

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

function Test-JsonEndpoint {
    param([string]$Name, [string]$Url, [scriptblock]$Predicate)
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    $safe = ($Name -replace '[^A-Za-z0-9._-]', '-')
    $LogPath = Join-Path $ResultRoot "$safe.log"
    try {
        $payload = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5 -ErrorAction Stop
        $payload | ConvertTo-Json -Depth 20 | Set-Content -Path $LogPath -Encoding UTF8
        if (-not (& $Predicate $payload)) {
            throw "endpoint returned JSON but did not satisfy the production-readiness predicate"
        }
        Write-Host "[PASS] $Name" -ForegroundColor Green
        return $true
    } catch {
        $_ | Out-String | Set-Content -Path $LogPath -Encoding UTF8
        $Failures.Add("$Name ($($_.Exception.Message))")
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        return $false
    }
}

function Test-LoopbackHttpEndpoint {
    param([string]$Url)
    try {
        $uri = [System.Uri]$Url
        return (
            $uri.Scheme -eq "http" -and
            $uri.Host -in @("127.0.0.1", "localhost", "::1") -and
            -not $uri.UserInfo -and
            -not $uri.Query -and
            -not $uri.Fragment
        )
    } catch {
        return $false
    }
}

# Offline gates first: fast and deterministic, no GPU/service dependency.
Invoke-Gate "image-quality-profile-tests" $PSScriptRoot $Python @("test_quality_profiles.py") | Out-Null
Invoke-Gate "prompt-quality-tests" $PSScriptRoot $Python @("test_prompt_quality.py") | Out-Null
Invoke-Gate "audio-quality-tests" $PSScriptRoot $Python @("test_audio_quality.py") | Out-Null

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

if ($RequireGateway) {
    if (-not (Test-LoopbackHttpEndpoint $GatewayEndpoint)) {
        $Failures.Add("Gateway endpoint must be loopback HTTP: $GatewayEndpoint")
        Write-Host "[FAIL] Gateway endpoint must be loopback HTTP" -ForegroundColor Red
    } else {
        $powershell = (Get-Process -Id $PID).Path
        Invoke-Gate "gateway-native-image-roundtrip" $PSScriptRoot $powershell @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "RUN-GATEWAY-QUALITY-SMOKE.ps1"),
            "-Python", $Python,
            "-GatewayBase", $GatewayEndpoint,
            "-ComfyEndpoint", $ComfyEndpoint,
            "-Profile", "quality",
            "-Seed", "1337",
            "-Output", (Join-Path $ResultRoot "gateway\smoke.png")
        ) | Out-Null
    }
}

if (-not $SkipKokoro) {
    $texts = "neutral"
    if ($Mode -eq "standard") { $texts = "neutral,numbers" }
    if ($Mode -eq "full") { $texts = "neutral,numbers,expressive,technical,proper_nouns" }
    Invoke-Gate "kokoro-golden-audio" $PSScriptRoot $Python @(
        "kokoro-quality-test.py",
        "--endpoint", $KokoroEndpoint,
        "--texts", $texts,
        "--output", (Join-Path $ResultRoot "kokoro")
    ) | Out-Null
    if ($Mode -eq "full") {
        Invoke-Gate "kokoro-runtime-attestation" $PSScriptRoot $Python @(
            "kokoro-runtime-snapshot.py",
            "--root", $KokoroRoot,
            "--endpoint", $KokoroEndpoint,
            "--output", $KokoroRuntimeEvidence,
            "--require-complete"
        ) | Out-Null
    }
}

if (-not $Skip3D) {
    if (-not (Test-Path (Join-Path $ThreeDRoot "pyproject.toml"))) {
        $Failures.Add("EVAVO 3D Studio not found at $ThreeDRoot")
        Write-Host "[FAIL] EVAVO 3D Studio not found at $ThreeDRoot" -ForegroundColor Red
    } else {
        # 3D Studio already owns candidate comparison, topology/UV/tangent/LOD,
        # Blender finishing, material evidence and runtime certification. Reuse
        # those governed checks rather than duplicating weaker mesh heuristics.
        Invoke-Gate "3d-studio-doctor" $ThreeDRoot $Python @("-m", "evavo_3d_studio", "doctor") | Out-Null
        if ($Mode -in @("standard", "full")) {
            Invoke-Gate "3d-studio-toolchain" $ThreeDRoot $Python @("-m", "evavo_3d_studio", "toolchain", "inspect") | Out-Null
            Invoke-Gate "3d-studio-providers" $ThreeDRoot $Python @("-m", "evavo_3d_studio", "providers", "list") | Out-Null
            $brief = Join-Path $ThreeDRoot "examples\rainy-red-bicycle.brief.json"
            if (Test-Path $brief) {
                Invoke-Gate "3d-studio-brief-validate" $ThreeDRoot $Python @("-m", "evavo_3d_studio", "brief", "validate", $brief) | Out-Null
                $planOutput = Join-Path $ResultRoot "3d-studio\rainy-red-bicycle-plan.json"
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $planOutput) | Out-Null
                Invoke-Gate "3d-studio-plan-compile" $ThreeDRoot $Python @("-m", "evavo_3d_studio", "plan", "compile", $brief, "--vram", "12", "--output", $planOutput) | Out-Null
            } else {
                $Failures.Add("3D Studio example brief missing: $brief")
                Write-Host "[FAIL] 3D Studio example brief missing: $brief" -ForegroundColor Red
            }
        }
        if ($Mode -eq "full") {
            Invoke-Gate "3d-studio-regression-suite" $ThreeDRoot $Python @("scripts\check.py") | Out-Null
            $snapshotArgs = @(
                "studio-runtime-snapshot.py", "3d",
                "--root", $ThreeDRoot,
                "--python", $Python,
                "--output", $ThreeDRuntimeEvidence,
                "--require-complete"
            )
            if ($Require3DExecution) {
                $snapshotArgs += @("--worker-endpoint", $ThreeDWorkerEndpoint)
            }
            Invoke-Gate "3d-runtime-attestation" $PSScriptRoot $Python $snapshotArgs | Out-Null
        }
        if ($Require3DExecution) {
            if (-not (Test-LoopbackHttpEndpoint $ThreeDWorkerEndpoint)) {
                $Failures.Add("3D execution worker endpoint must be loopback HTTP: $ThreeDWorkerEndpoint")
                Write-Host "[FAIL] 3D execution worker endpoint must be loopback HTTP" -ForegroundColor Red
            } else {
                $workerBase = $ThreeDWorkerEndpoint.TrimEnd('/')
                Test-JsonEndpoint "3d-studio-execution-worker-health" "$workerBase/api/v1/health" {
                    param($payload)
                    return (
                        $payload.ok -eq $true -and
                        $payload.service -eq "evavo-3d-agent-worker" -and
                        $payload.executionEnabled -eq $true -and
                        $payload.authority -eq "token-gated-candidate-production-only"
                    )
                } | Out-Null

                Test-JsonEndpoint "3d-studio-execution-worker-capabilities" "$workerBase/api/v1/capabilities" {
                    param($payload)
                    $requiredOperations = @(
                        "pipeline.generate-candidates",
                        "pipeline.finish-selected",
                        "pipeline.full-candidate",
                        "web-delivery.execute"
                    )
                    foreach ($operation in $requiredOperations) {
                        if ($payload.operations -notcontains $operation) { return $false }
                    }
                    return (
                        $payload.submit -eq $true -and
                        $payload.status -eq $true -and
                        $payload.automaticApproval -eq $false -and
                        $payload.canonicalPromotion -eq $false -and
                        $payload.gitMutation -eq $false -and
                        $payload.deployment -eq $false -and
                        $payload.publication -eq $false -and
                        $payload.clientRelease -eq $false
                    )
                } | Out-Null
            }
        }
    }
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
            Invoke-Gate "atmosphere-runtime-attestation" $PSScriptRoot $Python @(
                "studio-runtime-snapshot.py", "atmosphere",
                "--root", $AtmosphereRoot,
                "--output", $AtmosphereRuntimeEvidence,
                "--require-complete"
            ) | Out-Null
        }
    }
}

$Finished = Get-Date
$Summary = [ordered]@{
    schemaVersion = 5
    mode = $Mode
    startedAt = $Started.ToString("o")
    finishedAt = $Finished.ToString("o")
    durationSeconds = [math]::Round(($Finished - $Started).TotalSeconds, 3)
    comfyEndpoint = $ComfyEndpoint
    kokoroEndpoint = $KokoroEndpoint
    kokoroRoot = $KokoroRoot
    gatewayEndpoint = $GatewayEndpoint
    requireGateway = [bool]$RequireGateway
    atmosphereRoot = $AtmosphereRoot
    threeDRoot = $ThreeDRoot
    threeDWorkerEndpoint = $ThreeDWorkerEndpoint
    require3DExecution = [bool]$Require3DExecution
    threeDAuthorityContractChecked = [bool]$Require3DExecution
    runtimeEvidence = [ordered]@{
        kokoro = if ($Mode -eq "full" -and -not $SkipKokoro) { $KokoroRuntimeEvidence } else { $null }
        threeD = if ($Mode -eq "full" -and -not $Skip3D) { $ThreeDRuntimeEvidence } else { $null }
        atmosphere = if ($Mode -eq "full" -and -not $SkipAtmosphere) { $AtmosphereRuntimeEvidence } else { $null }
    }
    resultRoot = $ResultRoot
    ok = ($Failures.Count -eq 0)
    failures = @($Failures)
}
$Summary | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $ResultRoot "release-gate.json") -Encoding UTF8

Write-Host ""
Write-Host "Results: $ResultRoot"
if ($Failures.Count -gt 0) {
    Write-Host "PRODUCTION QUALITY GATE FAILED" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "PRODUCTION QUALITY GATE PASSED" -ForegroundColor Green
exit 0
