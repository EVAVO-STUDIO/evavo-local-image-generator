param(
    [switch]$Monitor,
    [switch]$SkipInstall,
    [int]$Interval = 5
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$PythonExe = $null
$PythonArgs = @()

if (Get-Command python -ErrorAction SilentlyContinue) {
    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) { $PythonExe = 'python' }
    } catch { }
}

if (-not $PythonExe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    try {
        & py -3 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $PythonExe = 'py'
            $PythonArgs = @('-3')
        }
    } catch { }
}

if (-not $PythonExe) {
    throw 'Python 3.10+ was not found on PATH.'
}

$VersionJson = & $PythonExe @PythonArgs -c "import json,sys; print(json.dumps({'major':sys.version_info.major,'minor':sys.version_info.minor,'version':sys.version.split()[0]}))"
$Version = $VersionJson | ConvertFrom-Json
if ($Version.major -lt 3 -or ($Version.major -eq 3 -and $Version.minor -lt 10)) {
    throw "Python 3.10+ is required. Found $($Version.version)."
}
Write-Host "Python $($Version.version) OK"

$ImportCheck = 'import fastapi,uvicorn,pydantic,aiohttp,websockets; print("All imports OK")'
& $PythonExe @PythonArgs -c $ImportCheck *> $null
if ($LASTEXITCODE -ne 0) {
    if ($SkipInstall) { throw 'Gateway Python dependencies are missing and -SkipInstall was supplied.' }
    Write-Host 'Installing gateway dependencies from requirements.txt...'
    & $PythonExe @PythonArgs -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}

& $PythonExe @PythonArgs -c $ImportCheck
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }

if (-not $env:EVAVO_GATEWAY_PORT) { $env:EVAVO_GATEWAY_PORT = '8000' }
if (-not $env:EVAVO_COMFYUI_ENDPOINT) { $env:EVAVO_COMFYUI_ENDPOINT = 'http://127.0.0.1:8188' }
if (-not $env:EVAVO_KOKORO_ENDPOINT) { $env:EVAVO_KOKORO_ENDPOINT = 'http://127.0.0.1:8880' }

if ($Monitor) {
    & $PythonExe @PythonArgs EVAVO-SERVICE-MANAGER.py monitor --interval $Interval
    exit $LASTEXITCODE
}

& $PythonExe @PythonArgs EVAVO-SERVICE-MANAGER.py start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'EVAVO Gateway: http://127.0.0.1:8000'
Write-Host 'API docs:      http://127.0.0.1:8000/docs'
Write-Host 'Health:        http://127.0.0.1:8000/health'
