# Store/remove the OpenAI Secure MCP Tunnel runtime key using Windows DPAPI.
# The encrypted blob can only be decrypted by the same Windows user on the same
# machine. The plaintext key is never written to disk by this script.

param(
    [switch]$FromEnvironment,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is unavailable; Windows DPAPI tunnel-key storage cannot be configured."
}

$secureDir = Join-Path $env:LOCALAPPDATA "EVAVO\Secure"
$keyPath = Join-Path $secureDir "chatgpt-tunnel-runtime-key.dpapi"

if ($Remove) {
    Remove-Item -Path $keyPath -Force -ErrorAction SilentlyContinue
    Write-Host "Removed the EVAVO ChatGPT tunnel runtime-key blob." -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Force -Path $secureDir | Out-Null

if ($FromEnvironment) {
    if (-not $env:CONTROL_PLANE_API_KEY) {
        throw "CONTROL_PLANE_API_KEY is not set in this process. Set it temporarily, then rerun with -FromEnvironment."
    }
    $secure = ConvertTo-SecureString -String $env:CONTROL_PLANE_API_KEY -AsPlainText -Force
}
else {
    Write-Host "Enter the OpenAI tunnel runtime API key. It will be stored only as a Windows DPAPI-encrypted blob." -ForegroundColor Cyan
    $secure = Read-Host "CONTROL_PLANE_API_KEY" -AsSecureString
}

$encrypted = ConvertFrom-SecureString -SecureString $secure
if (-not $encrypted) {
    throw "Windows DPAPI did not produce an encrypted value."
}
$encrypted | Set-Content -Path $keyPath -Encoding UTF8

# Verify immediately in the same user context without printing the plaintext.
try {
    $roundTrip = Get-Content $keyPath -Raw | ConvertTo-SecureString
    $credential = New-Object System.Management.Automation.PSCredential("evavo-tunnel", $roundTrip)
    $plain = $credential.GetNetworkCredential().Password
    if (-not $plain) {
        throw "decrypted key was empty"
    }
}
finally {
    $plain = $null
    $credential = $null
}

Write-Host "OpenAI tunnel runtime key stored with Windows DPAPI:" -ForegroundColor Green
Write-Host "  $keyPath" -ForegroundColor Green
Write-Host "The plaintext key was not written to the repository, Claude config, or Windows Startup." -ForegroundColor Green
