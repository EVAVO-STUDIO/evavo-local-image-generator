#!/usr/bin/env pwsh
<#
.SYNOPSIS
EVAVO Complete Automated Startup & Generation System
Starts ComfyUI, waits for readiness, monitors health, and runs autonomous generation

.DESCRIPTION
One-command system to:
1. Launch ComfyUI server in background
2. Wait for service readiness with health checks
3. Verify models are loaded
4. Run autonomous image generation
5. Monitor and log all operations

.NOTES
Author: EVAVO Studio
Version: 2.0.0
Platform: Windows PowerShell 7+
#>

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Start", "Monitor", "Full")]
    [string]$Mode = "Full"
)

# Configuration
$ComfyUIPath = "C:\AI\ComfyUI"
$RepoPath = "C:\Gitrepos\evavo-local-image-generator"
$ComfyUIURL = "http://127.0.0.1:8188"
$LogDir = "C:\Gitrepos\evavo-logs"
$MaxWaitSeconds = 120
$HealthCheckInterval = 2

# Color output
function Write-Status {
    param(
        [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "ERROR", "WARNING")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        default { "White" }
    }

    $msg = "[$timestamp] [$Level] $Message"
    Write-Host $msg -ForegroundColor $color
}

function Write-Banner {
    param([string]$Title)
    
    $border = "=" * 70
    Write-Host ""
    Write-Host $border -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host $border -ForegroundColor Cyan
    Write-Host ""
}

# Phase 1: Start ComfyUI
function Start-ComfyUI {
    Write-Banner "STARTING COMFYUI SERVER"

    if (-not (Test-Path $ComfyUIPath)) {
        Write-Status "ComfyUI not found at $ComfyUIPath" "ERROR"
        return $false
    }

    Write-Status "Launching ComfyUI..." "INFO"
    
    try {
        $process = Start-Process `
            -FilePath "python" `
            -ArgumentList "main.py" `
            -WorkingDirectory $ComfyUIPath `
            -WindowStyle Normal `
            -PassThru
        
        Write-Status "✓ ComfyUI started (PID: $($process.Id))" "SUCCESS"
        return $process
        
    } catch {
        Write-Status "Failed to start ComfyUI: $_" "ERROR"
        return $false
    }
}

# Phase 2: Wait for ComfyUI readiness
function Wait-ForComfyUI {
    Write-Banner "WAITING FOR COMFYUI READINESS"

    $startTime = Get-Date
    $attempt = 0

    while ((Get-Date) - $startTime -lt [TimeSpan]::FromSeconds($MaxWaitSeconds)) {
        $attempt++
        
        try {
            $response = Invoke-WebRequest -Uri "$ComfyUIURL/system_stats" `
                -TimeoutSec 5 `
                -ErrorAction Stop

            if ($response.StatusCode -eq 200) {
                Write-Status "✓ ComfyUI is ready!" "SUCCESS"
                
                $stats = $response.Content | ConvertFrom-Json
                Write-Status "  System ready for generation" "SUCCESS"
                return $true
            }
        }
        catch {
            $elapsed = ((Get-Date) - $startTime).TotalSeconds
            Write-Status "  Attempt $attempt - Waiting for ComfyUI ({0:F1}s)..." -f $elapsed "INFO"
            Start-Sleep -Seconds $HealthCheckInterval
        }
    }

    Write-Status "✗ ComfyUI failed to start within $MaxWaitSeconds seconds" "ERROR"
    return $false
}

# Phase 3: Check models
function Check-Models {
    Write-Banner "CHECKING AVAILABLE MODELS"

    try {
        $response = Invoke-WebRequest -Uri "$ComfyUIURL/models" `
            -TimeoutSec 10 `
            -ErrorAction Stop

        $models = $response.Content | ConvertFrom-Json
        
        Write-Status "✓ Checkpoints: $($models.checkpoints.Count)" "SUCCESS"
        Write-Status "✓ VAE: $($models.vae.Count)" "SUCCESS"
        Write-Status "✓ LoRAs: $($models.loras.Count)" "SUCCESS"
        Write-Status "✓ Upscalers: $($models.upscale_models.Count)" "SUCCESS"
        
        return $true
    }
    catch {
        Write-Status "Warning: Could not verify models" "WARNING"
        return $true
    }
}

# Phase 4: Run autonomous generation
function Run-AutonomousGeneration {
    Write-Banner "STARTING AUTONOMOUS GENERATION"

    if (-not (Test-Path $RepoPath)) {
        Write-Status "Repository not found at $RepoPath" "ERROR"
        return $false
    }

    Write-Status "Launching autonomous generation..." "INFO"

    try {
        $logFile = Join-Path $LogDir "generation-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
        
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }

        Push-Location $RepoPath
        
        & python run_autonomous.py *>&1 | Tee-Object -FilePath $logFile
        
        $exitCode = $LASTEXITCODE
        Pop-Location

        if ($exitCode -eq 0) {
            Write-Status "✓ Generation completed successfully" "SUCCESS"
            return $true
        }
        else {
            Write-Status "✗ Generation encountered errors (exit code: $exitCode)" "ERROR"
            return $false
        }
    }
    catch {
        Write-Status "Failed to run generation: $_" "ERROR"
        return $false
    }
}

# Main execution
try {
    Write-Banner "EVAVO COMPLETE STARTUP & GENERATION SYSTEM"
    Write-Status "Mode: $Mode" "INFO"

    $ComfyUIProcess = $null

    # Start ComfyUI
    $ComfyUIProcess = Start-ComfyUI
    if (-not $ComfyUIProcess) {
        exit 1
    }

    # Wait for readiness
    Start-Sleep -Seconds 3
    
    if (-not (Wait-ForComfyUI)) {
        if ($ComfyUIProcess) {
            Stop-Process -InputObject $ComfyUIProcess -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }

    Start-Sleep -Seconds 2

    # Check models
    Check-Models

    # Run generation if in Full or Start+Run mode
    if ($Mode -eq "Full") {
        $success = Run-AutonomousGeneration
        
        Write-Banner "COMPLETION STATUS"
        if ($success) {
            Write-Status "✓ All operations completed successfully" "SUCCESS"
        }
        else {
            Write-Status "✗ Some operations encountered errors" "ERROR"
        }
    }
    else {
        Write-Banner "SYSTEM READY"
        Write-Status "✓ ComfyUI is running and ready for generation" "SUCCESS"
        Write-Status "  URL: $ComfyUIURL" "INFO"
        Write-Status "  You can now run: python run_autonomous.py" "INFO"
        Write-Status "  Press Ctrl+C to stop ComfyUI" "WARNING"
        
        # Keep running
        while ($true) {
            Start-Sleep -Seconds 10
        }
    }
}
catch {
    Write-Status "Critical error: $_" "ERROR"
    exit 1
}
