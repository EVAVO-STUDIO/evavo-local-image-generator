# Compatibility shim for historical installation verification.
# The authoritative verifier compiles current Python, parses canonical
# PowerShell scripts and runs every modern safety/integration suite.

param(
    [switch]$StructuralOnly,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python 3.10+ was not found."
    }
    $python = $command.Source
}

$args = @((Join-Path $PSScriptRoot "verify-evavo.py"), "--require-powershell")
if (-not $StructuralOnly) {
    $args += "--full"
}
if ($Json) {
    $args += "--json"
}

& $python @args
exit $LASTEXITCODE
