param(
    [string]$Python = "python",
    [string]$KokoroEndpoint = "http://127.0.0.1:8880",
    [string]$Voices = "af_heart,af_bella,bf_emma",
    [double]$Speed = 1.0,
    [string]$OutputRoot = ".evavo\quality-results\kokoro-voice-comparison"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot

Write-Host "EVAVO KOKORO VOICE COMPARISON" -ForegroundColor Cyan
Write-Host "Endpoint: $KokoroEndpoint"
Write-Host "Voices: $Voices"
Write-Host "Speed: $Speed"
Write-Host ""

& $Python .\test_audio_quality.py
if ($LASTEXITCODE -ne 0) { throw "Offline audio-quality regressions failed." }

$resolved = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputRoot))
New-Item -ItemType Directory -Force -Path $resolved | Out-Null
$started = Get-Date

& $Python .\kokoro-quality-test.py `
    --endpoint $KokoroEndpoint `
    --voices $Voices `
    --texts "neutral,numbers,expressive,technical,proper_nouns" `
    --speed $Speed `
    --output $resolved
if ($LASTEXITCODE -ne 0) { throw "Kokoro voice comparison failed technical QC." }

$review = Get-ChildItem -Path $resolved -Filter "human_review.csv" -Recurse -File |
    Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-2) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $review) { throw "Voice comparison completed but no new human_review.csv was found." }

Write-Host ""
Write-Host "Voice comparison technical checks passed." -ForegroundColor Green
Write-Host "Listening review: $($review.FullName)"
Write-Host "Score every sample before choosing a production voice. Do not select from one flattering sentence."
