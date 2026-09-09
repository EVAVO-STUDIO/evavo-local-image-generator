param(
    [string]$ComfyRoot = "C:\AI\ComfyUI",
    [string]$KokoroRoot = "C:\AI\Kokoro-FastAPI",
    [string]$AtmosphereRoot = "C:\GitRepos\atmosphere-studio",
    [string]$ThreeDRoot = "C:\GitRepos\evavo-3d-studio",
    [switch]$UseNextComfy,
    [switch]$Start3DWorker,
    [switch]$StartGateway,
    [string]$ThreeDWorkspaceRoot = "C:\EVAVO-3D-WORK",
    [ValidateRange(1024, 65535)]
    [int]$ThreeDWorkerPort = 4314,
    [ValidateRange(1024, 65535)]
    [int]$GatewayPort = 8000,
    [ValidateSet("dev", "start")]
    [string]$AtmosphereMode = "dev",
    [string]$OutputRoot = "C:\AI\evavo-generation-results"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($UseNextComfy) {
    $ComfyRoot = "C:\AI\ComfyUI-next"
    $ComfyPort = 8189
} else {
    $ComfyPort = 8188
}

$ComfyEndpoint = "http://127.0.0.1:$ComfyPort"
$KokoroEndpoint = "http://127.0.0.1:8880"
$AtmosphereEndpoint = "http://127.0.0.1:3000"
$ThreeDWorkerEndpoint = "http://127.0.0.1:$ThreeDWorkerPort"
$GatewayEndpoint = "http://127.0.0.1:$GatewayPort"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogRoot = Join-Path $OutputRoot "service-logs\$Stamp"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Test-Endpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -lt 500) {
            return $true
        }
        return $false
    }
}

function Wait-Endpoint {
    param([string[]]$Urls, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        foreach ($url in $Urls) {
            if (Test-Endpoint $url) { return $url }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become healthy within $TimeoutSeconds seconds. Tried: $($Urls -join ', ')"
}

function Wait-JsonEndpoint {
    param(
        [string]$Url,
        [scriptblock]$Predicate,
        [int]$TimeoutSeconds
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $payload = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 4 -ErrorAction Stop
            if (& $Predicate $payload) { return $payload }
        } catch {
            # Readiness polling intentionally retries bounded connection/startup failures.
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "JSON service did not satisfy its readiness contract within $TimeoutSeconds seconds: $Url"
}

function Find-ComfyPython {
    param([string]$Root)
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe"),
        (Join-Path $Root "python_embeded\python.exe"),
        (Join-Path $Root "python_embedded\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Could not find the Python runtime for ComfyUI under $Root"
}

function Find-PythonForRepo {
    param([string]$Root)
    foreach ($candidate in @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe")
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Python 3 was not found for repository $Root"
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $safeName = $Name -replace '[^A-Za-z0-9._-]', '-'
    $stdout = Join-Path $LogRoot "$safeName.out.log"
    $stderr = Join-Path $LogRoot "$safeName.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
    Write-Host "[START] $Name PID $($process.Id)"
    return $process
}

function Test-GatewayQualityContract {
    param([string]$Endpoint)
    try {
        $payload = Invoke-RestMethod -Uri "$Endpoint/capabilities" -Method Get -TimeoutSec 5 -ErrorAction Stop
        $profiles = @($payload.image.quality_profiles)
        $receipt = @($payload.image.reproducible_receipt)
        return (
            $payload.image.ready -eq $true -and
            $payload.image.per_request_quality -eq $true -and
            $payload.image.hero_two_pass -eq $true -and
            $payload.image.lora -eq $true -and
            $profiles -contains "quality" -and
            $profiles -contains "hero" -and
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

Write-Host "EVAVO QUALITY STACK" -ForegroundColor Cyan
Write-Host "Logs: $LogRoot"
Write-Host ""

# ComfyUI
if (Test-Endpoint "$ComfyEndpoint/system_stats") {
    Write-Host "[OK] ComfyUI already healthy at $ComfyEndpoint" -ForegroundColor Green
} else {
    if (-not (Test-Path (Join-Path $ComfyRoot "main.py"))) {
        throw "ComfyUI main.py not found at $ComfyRoot"
    }
    if ($UseNextComfy -and (Test-Path (Join-Path $ComfyRoot "START-EVAVO-COMFYUI-NEXT.ps1"))) {
        Start-LoggedProcess "comfyui-next" "powershell.exe" @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $ComfyRoot "START-EVAVO-COMFYUI-NEXT.ps1")
        ) $ComfyRoot | Out-Null
    } else {
        $python = Find-ComfyPython $ComfyRoot
        $arguments = @(
            (Join-Path $ComfyRoot "main.py"),
            "--listen", "127.0.0.1",
            "--port", "$ComfyPort",
            "--preview-method", "none",
            "--reserve-vram", "1"
        )
        Start-LoggedProcess "comfyui" $python $arguments $ComfyRoot | Out-Null
    }
    Wait-Endpoint @("$ComfyEndpoint/system_stats", "$ComfyEndpoint/queue", $ComfyEndpoint) 300 | Out-Null
    Write-Host "[OK] ComfyUI healthy at $ComfyEndpoint" -ForegroundColor Green
}

# Kokoro-FastAPI
if (Test-Endpoint "$KokoroEndpoint/v1/audio/voices") {
    Write-Host "[OK] Kokoro already healthy at $KokoroEndpoint" -ForegroundColor Green
} else {
    $kokoroStarter = Join-Path $KokoroRoot "start-gpu.ps1"
    if (-not (Test-Path $kokoroStarter)) {
        throw "Kokoro GPU starter not found: $kokoroStarter"
    }
    Start-LoggedProcess "kokoro" "powershell.exe" @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $kokoroStarter
    ) $KokoroRoot | Out-Null
    Wait-Endpoint @("$KokoroEndpoint/v1/audio/voices", "$KokoroEndpoint/docs") 300 | Out-Null
    Write-Host "[OK] Kokoro healthy at $KokoroEndpoint" -ForegroundColor Green
}

# Optional bounded EVAVO 3D Studio execution worker.
# This is opt-in because the default Studio MCP/API intentionally remain non-executing.
if ($Start3DWorker) {
    if (-not (Test-Path (Join-Path $ThreeDRoot "pyproject.toml"))) {
        throw "EVAVO 3D Studio not found at $ThreeDRoot"
    }
    if ([string]::IsNullOrWhiteSpace($env:EVAVO_3D_AGENT_EXECUTION_TOKEN) -or $env:EVAVO_3D_AGENT_EXECUTION_TOKEN.Length -lt 32) {
        throw "Start3DWorker requires EVAVO_3D_AGENT_EXECUTION_TOKEN with at least 32 characters. The launcher will not generate or log this token."
    }

    $sourceRoot = [System.IO.Path]::GetFullPath($ThreeDRoot).TrimEnd('\')
    $workspaceRoot = [System.IO.Path]::GetFullPath($ThreeDWorkspaceRoot).TrimEnd('\')
    if ($workspaceRoot -eq $sourceRoot -or $workspaceRoot.StartsWith($sourceRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "ThreeDWorkspaceRoot must be outside the 3D Studio source repository."
    }
    New-Item -ItemType Directory -Force -Path $workspaceRoot | Out-Null

    $env:EVAVO_3D_AGENT_EXECUTION_ENABLED = "1"
    $env:EVAVO_3D_AGENT_WORKSPACE_ROOT = $workspaceRoot

    $healthUrl = "$ThreeDWorkerEndpoint/api/v1/health"
    $healthPredicate = {
        param($payload)
        return (
            $payload.ok -eq $true -and
            $payload.service -eq "evavo-3d-agent-worker" -and
            $payload.executionEnabled -eq $true -and
            $payload.authority -eq "token-gated-candidate-production-only"
        )
    }

    $alreadyReady = $false
    try {
        $existing = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 4 -ErrorAction Stop
        $alreadyReady = (& $healthPredicate $existing)
    } catch {
        $alreadyReady = $false
    }

    if ($alreadyReady) {
        Write-Host "[OK] 3D execution worker already healthy at $ThreeDWorkerEndpoint" -ForegroundColor Green
    } else {
        $threeDPython = Find-PythonForRepo $ThreeDRoot
        Start-LoggedProcess "evavo-3d-agent-worker" $threeDPython @(
            "-m", "evavo_3d_studio.agent_worker",
            "serve", "--host", "127.0.0.1", "--port", "$ThreeDWorkerPort"
        ) $ThreeDRoot | Out-Null
        Wait-JsonEndpoint $healthUrl $healthPredicate 120 | Out-Null
        Write-Host "[OK] 3D execution worker healthy at $ThreeDWorkerEndpoint" -ForegroundColor Green
    }

    $capabilities = Invoke-RestMethod -Uri "$ThreeDWorkerEndpoint/api/v1/capabilities" -Method Get -TimeoutSec 5 -ErrorAction Stop
    $requiredOperations = @(
        "pipeline.generate-candidates",
        "pipeline.finish-selected",
        "pipeline.full-candidate",
        "web-delivery.execute"
    )
    foreach ($operation in $requiredOperations) {
        if ($capabilities.operations -notcontains $operation) {
            throw "3D worker is missing required bounded operation: $operation"
        }
    }
    if (
        $capabilities.automaticApproval -ne $false -or
        $capabilities.canonicalPromotion -ne $false -or
        $capabilities.gitMutation -ne $false -or
        $capabilities.deployment -ne $false -or
        $capabilities.publication -ne $false -or
        $capabilities.clientRelease -ne $false
    ) {
        throw "3D worker authority exceeds the approved candidate-production boundary."
    }
}

# Atmosphere Studio
if (Test-Endpoint $AtmosphereEndpoint) {
    Write-Host "[OK] Atmosphere Studio already healthy at $AtmosphereEndpoint" -ForegroundColor Green
} else {
    if (-not (Test-Path (Join-Path $AtmosphereRoot "package.json"))) {
        throw "Atmosphere Studio package.json not found at $AtmosphereRoot"
    }
    $npm = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { "npm.cmd" } else { "npm" }
    if ($AtmosphereMode -eq "start" -and -not (Test-Path (Join-Path $AtmosphereRoot ".next"))) {
        Write-Host "[INFO] Production Atmosphere build is missing; running npm run build first."
        Push-Location $AtmosphereRoot
        try {
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw "Atmosphere npm run build failed" }
        } finally {
            Pop-Location
        }
    }
    Start-LoggedProcess "atmosphere" $npm @("run", $AtmosphereMode) $AtmosphereRoot | Out-Null
    Wait-Endpoint @($AtmosphereEndpoint) 180 | Out-Null
    Write-Host "[OK] Atmosphere Studio healthy at $AtmosphereEndpoint" -ForegroundColor Green
}

# Optional unified HTTP compatibility gateway. Bind it to the same selected
# ComfyUI runtime so 8188/8189 comparisons remain meaningful end to end.
if ($StartGateway) {
    if (Test-GatewayQualityContract $GatewayEndpoint) {
        Write-Host "[OK] EVAVO gateway already exposes the quality contract at $GatewayEndpoint" -ForegroundColor Green
    } else {
        if (Test-Endpoint "$GatewayEndpoint/health") {
            throw "An EVAVO gateway is already running at $GatewayEndpoint but does not expose the current quality contract. Restart that gateway so it loads the current main branch before retrying -StartGateway."
        }
        $gatewayStarter = Join-Path $PSScriptRoot "START-GATEWAY.ps1"
        if (-not (Test-Path -LiteralPath $gatewayStarter -PathType Leaf)) {
            throw "Gateway starter not found: $gatewayStarter"
        }
        $env:COMFYUI_ENDPOINT = $ComfyEndpoint
        $env:EVAVO_COMFYUI_ENDPOINT = $ComfyEndpoint
        $env:EVAVO_GATEWAY_HOST = "127.0.0.1"
        $env:EVAVO_GATEWAY_PORT = "$GatewayPort"
        Start-LoggedProcess "evavo-gateway-bootstrap" "powershell.exe" @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $gatewayStarter,
            "-SkipInstall", "-SkipValidation"
        ) $PSScriptRoot | Out-Null

        $gatewayPredicate = {
            param($payload)
            $profiles = @($payload.image.quality_profiles)
            $receipt = @($payload.image.reproducible_receipt)
            return (
                $payload.image.ready -eq $true -and
                $payload.image.per_request_quality -eq $true -and
                $payload.image.hero_two_pass -eq $true -and
                $payload.image.lora -eq $true -and
                $profiles -contains "quality" -and
                $profiles -contains "hero" -and
                $receipt -contains "seed" -and
                $receipt -contains "workflow_sha256" -and
                $receipt -contains "quality_profile" -and
                $receipt -contains "output_width" -and
                $receipt -contains "output_height"
            )
        }
        Wait-JsonEndpoint "$GatewayEndpoint/capabilities" $gatewayPredicate 120 | Out-Null
        Write-Host "[OK] EVAVO gateway quality contract healthy at $GatewayEndpoint" -ForegroundColor Green
    }
}

$summary = [ordered]@{
    schemaVersion = 3
    startedAt = (Get-Date).ToString("o")
    useNextComfy = [bool]$UseNextComfy
    comfyRoot = $ComfyRoot
    comfyEndpoint = $ComfyEndpoint
    kokoroRoot = $KokoroRoot
    kokoroEndpoint = $KokoroEndpoint
    atmosphereRoot = $AtmosphereRoot
    atmosphereEndpoint = $AtmosphereEndpoint
    atmosphereMode = $AtmosphereMode
    threeDRoot = $ThreeDRoot
    threeDWorkerRequested = [bool]$Start3DWorker
    threeDWorkerEndpoint = if ($Start3DWorker) { $ThreeDWorkerEndpoint } else { $null }
    threeDWorkspaceRoot = if ($Start3DWorker) { $ThreeDWorkspaceRoot } else { $null }
    gatewayRequested = [bool]$StartGateway
    gatewayEndpoint = if ($StartGateway) { $GatewayEndpoint } else { $null }
    logRoot = $LogRoot
}
$summary | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $LogRoot "stack.json") -Encoding UTF8

Write-Host ""
Write-Host "EVAVO quality stack is healthy." -ForegroundColor Green
Write-Host "Run the quality gate from the generator repo:"
$qualityArgs = @(".\RUN-PRODUCTION-QUALITY.ps1", "-Mode", "standard")
if ($UseNextComfy) {
    $qualityArgs += @("-ComfyEndpoint", "http://127.0.0.1:8189")
}
if ($Start3DWorker) {
    $qualityArgs += @("-Require3DExecution", "-ThreeDWorkerEndpoint", $ThreeDWorkerEndpoint)
}
Write-Host ("  " + ($qualityArgs -join " "))
if ($StartGateway) {
    Write-Host "Gateway end-to-end smoke:"
    Write-Host "  python .\gateway-smoke-test.py --base $GatewayEndpoint --profile quality --seed 1337"
}
