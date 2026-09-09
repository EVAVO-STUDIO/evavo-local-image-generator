# Start the optional loopback HTTP compatibility gateway.
# Production health requires native ComfyUI; deterministic mock fallback is not
# accepted by EVAVO-SERVICE-MANAGER.py.

param(
    [switch]$Monitor,
    [switch]$SkipInstall,
    [switch]$SkipValidation,
    [int]$Interval = 5
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Interval -lt 1) {
    throw "-Interval must be at least 1 second."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python 3.10+ was not found."
    }
    $python = $command.Source
}

& $python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python failed to run."
}

if (-not $SkipInstall) {
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
}

if (-not $SkipValidation) {
    & $python (Join-Path $PSScriptRoot "verify-evavo.py") --require-powershell
    if ($LASTEXITCODE -ne 0) {
        throw "Repository structural verification failed."
    }
}

if (-not $env:EVAVO_GATEWAY_HOST) { $env:EVAVO_GATEWAY_HOST = "127.0.0.1" }
if (-not $env:EVAVO_GATEWAY_PORT) { $env:EVAVO_GATEWAY_PORT = "8000" }
if (-not $env:COMFYUI_ENDPOINT -and -not $env:EVAVO_COMFYUI_ENDPOINT) {
    $env:COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
}

# Resolve the governed Wan publication through Video Studio when callers have
# not explicitly selected a model. The resolver performs deterministic lookup
# only; it never scans disks or downloads model bytes. Failure is non-fatal so
# image/audio/3D gateway capabilities remain available while video stays honest.
if (-not $env:EVAVO_VIDEO_PROVIDER_ARGV -and -not $env:EVAVO_WAN21_MODEL_DIR) {
    $videoCandidates = @()
    if ($env:EVAVO_VIDEO_STUDIO_DIR) {
        $videoCandidates += $env:EVAVO_VIDEO_STUDIO_DIR
    }
    $repoParent = Split-Path -Parent $PSScriptRoot
    $videoCandidates += (Join-Path $repoParent "evavo-video-studio")
    $videoCandidates += (Join-Path $repoParent "video-studio")

    foreach ($candidate in $videoCandidates) {
        if (-not $candidate) { continue }
        $videoRoot = [System.IO.Path]::GetFullPath($candidate)
        $resolver = Join-Path $videoRoot "tools\resolve_wan21_model.py"
        $worker = Join-Path $videoRoot "tools\wan21_t2v_worker.py"
        if (-not (Test-Path -LiteralPath $resolver -PathType Leaf)) { continue }
        if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) { continue }

        $videoPython = Join-Path $videoRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $videoPython -PathType Leaf)) {
            $videoPython = $python
        }

        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $resolverOutput = @(& $videoPython $resolver 2>$null)
            $resolverExit = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorPreference
        }
        if ($resolverExit -ne 0 -or $resolverOutput.Count -eq 0) { continue }

        try {
            $resolved = ($resolverOutput | Select-Object -Last 1) | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            continue
        }
        if ($resolved.ok -ne $true -or -not $resolved.modelDir -or -not $resolved.modelManifestSha256) { continue }

        $env:EVAVO_WAN21_MODEL_DIR = [string]$resolved.modelDir
        $env:EVAVO_WAN21_MODEL_MANIFEST_SHA256 = [string]$resolved.modelManifestSha256
        $env:EVAVO_VIDEO_STUDIO_DIR = $videoRoot
        Write-Host "Video Studio Wan model: $($resolved.modelDir)" -ForegroundColor DarkGreen
        break
    }
}

# Auto-discover the first-party Audio Studio provider in the normal sibling-repo
# layout. An explicit EVAVO_AUDIO_PROVIDER_ARGV always wins. The gateway provider
# contract is argv JSON rather than a shell command, preserving shell=False.
if (-not $env:EVAVO_AUDIO_PROVIDER_ARGV) {
    $audioCandidates = @()
    if ($env:EVAVO_AUDIO_STUDIO_DIR) {
        $audioCandidates += $env:EVAVO_AUDIO_STUDIO_DIR
    }
    $repoParent = Split-Path -Parent $PSScriptRoot
    $audioCandidates += (Join-Path $repoParent "evavo-audio-studio")
    $audioCandidates += (Join-Path $repoParent "audio-studio")

    foreach ($candidate in $audioCandidates) {
        if (-not $candidate) { continue }
        $audioRoot = [System.IO.Path]::GetFullPath($candidate)
        $audioWorker = Join-Path $audioRoot "worker_provider.py"
        if (-not (Test-Path -LiteralPath $audioWorker -PathType Leaf)) { continue }

        $audioPython = Join-Path $audioRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $audioPython -PathType Leaf)) {
            $audioPython = $python
        }

        $audioArgv = @(
            $audioPython,
            $audioWorker,
            "--request-json", "{request_json}",
            "--output-dir", "{output_dir}",
            "--task-id", "{task_id}"
        )
        $env:EVAVO_AUDIO_PROVIDER_ARGV = ConvertTo-Json -InputObject $audioArgv -Compress
        $env:EVAVO_AUDIO_STUDIO_DIR = $audioRoot
        if (-not $env:EVAVO_AUDIO_PROVIDER_TIMEOUT) {
            $env:EVAVO_AUDIO_PROVIDER_TIMEOUT = "7200"
        }
        Write-Host "Audio Studio provider: $audioWorker" -ForegroundColor DarkGreen
        break
    }
}

$manager = Join-Path $PSScriptRoot "EVAVO-SERVICE-MANAGER.py"
if ($Monitor) {
    & $python $manager monitor --interval $Interval
    exit $LASTEXITCODE
}

& $python $manager start
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "EVAVO native-image gateway is ready." -ForegroundColor Green
Write-Host "Gateway: http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)" -ForegroundColor Green
Write-Host "Docs:    http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)/docs" -ForegroundColor Green
Write-Host "Health:  http://$($env:EVAVO_GATEWAY_HOST):$($env:EVAVO_GATEWAY_PORT)/health" -ForegroundColor Green
