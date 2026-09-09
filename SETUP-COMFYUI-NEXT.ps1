param(
    [string]$CurrentRoot = "C:\AI\ComfyUI",
    [string]$TargetRoot = "C:\AI\ComfyUI-next",
    [ValidateSet("3.12", "3.13")]
    [string]$PythonVersion = "3.12",
    [int]$Port = 8189,
    [switch]$InstallCurrentCustomNodes
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([Parameter(Mandatory=$true)][string]$FilePath, [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Write-Host "> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $FilePath $($Arguments -join ' ')"
    }
}

function Assert-PathSafe {
    param([string]$PathValue)
    $full = [System.IO.Path]::GetFullPath($PathValue)
    if ($full.Length -lt 8 -or $full -eq [System.IO.Path]::GetPathRoot($full)) {
        throw "Refusing unsafe target path: $full"
    }
    return $full
}

$CurrentRoot = Assert-PathSafe $CurrentRoot
$TargetRoot = Assert-PathSafe $TargetRoot

if (-not (Test-Path (Join-Path $CurrentRoot "main.py"))) {
    throw "Current ComfyUI install was not found at $CurrentRoot"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required on PATH"
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' is required on PATH"
}

Write-Host ""
Write-Host "EVAVO SAFE COMFYUI NEXT SETUP" -ForegroundColor Cyan
Write-Host "Current install remains untouched: $CurrentRoot"
Write-Host "Parallel install:               $TargetRoot"
Write-Host "Parallel port:                  $Port"
Write-Host "Python:                         $PythonVersion"
Write-Host ""

if (-not (Test-Path $TargetRoot)) {
    Invoke-Checked git clone https://github.com/Comfy-Org/ComfyUI.git $TargetRoot
} elseif (-not (Test-Path (Join-Path $TargetRoot ".git")) -or -not (Test-Path (Join-Path $TargetRoot "main.py"))) {
    throw "Target already exists but does not look like a ComfyUI Git checkout: $TargetRoot"
} else {
    Write-Host "[OK] Existing parallel ComfyUI checkout detected; it will not be deleted or overwritten." -ForegroundColor Green
    Push-Location $TargetRoot
    try {
        Invoke-Checked git fetch --all --prune
        $status = & git status --porcelain
        if ($LASTEXITCODE -ne 0) { throw "git status failed" }
        if ([string]::IsNullOrWhiteSpace(($status -join "`n"))) {
            Invoke-Checked git pull --ff-only
        } else {
            Write-Warning "Target checkout has local changes. Skipping git pull so nothing is overwritten."
        }
    } finally {
        Pop-Location
    }
}

$Venv = Join-Path $TargetRoot ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Invoke-Checked py "-$PythonVersion" -m venv $Venv
}

Invoke-Checked $Python -m pip install --upgrade pip setuptools wheel

# Current ComfyUI stable NVIDIA guidance uses PyTorch CUDA 13.0. This is
# isolated inside C:\AI\ComfyUI-next and does not modify the working cu118 env.
Invoke-Checked $Python -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
Invoke-Checked $Python -m pip install -r (Join-Path $TargetRoot "requirements.txt")

$ModelConfig = Join-Path $TargetRoot "evavo-current-models.yaml"
$yamlRoot = $CurrentRoot -replace '\\','/'
@"
evavo_current_models:
  base_path: $yamlRoot/
  checkpoints: models/checkpoints/
  text_encoders: |
    models/text_encoders/
    models/clip/
  clip_vision: models/clip_vision/
  configs: models/configs/
  controlnet: models/controlnet/
  diffusion_models: |
    models/diffusion_models/
    models/unet/
  embeddings: models/embeddings/
  loras: models/loras/
  upscale_models: models/upscale_models/
  vae: models/vae/
  audio_encoders: models/audio_encoders/
  model_patches: models/model_patches/
"@ | Set-Content -Path $ModelConfig -Encoding UTF8

if ($InstallCurrentCustomNodes) {
    $SourceNodes = Join-Path $CurrentRoot "custom_nodes"
    $TargetNodes = Join-Path $TargetRoot "custom_nodes"
    if (Test-Path $SourceNodes) {
        Write-Warning "Custom nodes are the highest compatibility risk during a Python/Torch migration. Copying source folders only; their dependencies still need individual validation."
        Get-ChildItem $SourceNodes -Directory | ForEach-Object {
            $destination = Join-Path $TargetNodes $_.Name
            if (-not (Test-Path $destination)) {
                Copy-Item $_.FullName $destination -Recurse
            }
        }
    }
}

$Probe = @'
import json, platform, torch
print(json.dumps({
  "python": platform.python_version(),
  "torch": torch.__version__,
  "torch_cuda_build": torch.version.cuda,
  "cuda_available": torch.cuda.is_available(),
  "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
  "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if torch.cuda.is_available() else None,
}, indent=2))
if not torch.cuda.is_available():
    raise SystemExit(2)
'@
Invoke-Checked $Python -c $Probe

$Starter = Join-Path $TargetRoot "START-EVAVO-COMFYUI-NEXT.ps1"
$starterBody = @"
`$ErrorActionPreference = "Stop"
Set-Location "$TargetRoot"
& ".\.venv\Scripts\python.exe" ".\main.py" --listen 127.0.0.1 --port $Port --preview-method none --reserve-vram 1 --extra-model-paths-config ".\evavo-current-models.yaml"
exit `$LASTEXITCODE
"@
$starterBody | Set-Content -Path $Starter -Encoding UTF8

$Info = [ordered]@{
    createdAt = (Get-Date).ToString("o")
    currentRoot = $CurrentRoot
    targetRoot = $TargetRoot
    pythonVersion = $PythonVersion
    port = $Port
    endpoint = "http://127.0.0.1:$Port"
    modelConfig = $ModelConfig
    starter = $Starter
    currentInstallModified = $false
    customNodesCopied = [bool]$InstallCurrentCustomNodes
}
$Info | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $TargetRoot "evavo-next-runtime.json") -Encoding UTF8

Write-Host ""
Write-Host "[OK] Parallel ComfyUI runtime prepared without modifying $CurrentRoot" -ForegroundColor Green
Write-Host "Start it with:"
Write-Host "  & '$Starter'"
Write-Host "Then validate it from this repo with:"
Write-Host "  python quality-benchmark.py --endpoint http://127.0.0.1:$Port --profiles quality,euler_reference --prompts product,portrait --seeds 1337"
Write-Host ""
Write-Host "Do not promote the new runtime until core generation and required custom nodes pass fixed-seed comparisons."
