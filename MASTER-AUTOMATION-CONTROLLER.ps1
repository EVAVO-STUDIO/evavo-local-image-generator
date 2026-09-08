#!/usr/bin/env pwsh
<#
.SYNOPSIS
EVAVO Master Automation Controller - Complete Autonomous System
Full end-to-end automation with no manual intervention required

.DESCRIPTION
Single entry point for complete autonomous operation:
- Auto-detects system state
- Auto-starts services as needed
- Auto-recovers from failures
- Auto-monitors performance
- Auto-generates images on schedule
- Auto-logs everything

.NOTES
Author: EVAVO Studio
Version: 2.0.0
Mode: FULLY AUTONOMOUS
#>

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Full", "Monitor", "Service", "Test", "Status")]
    [string]$Mode = "Full",
    
    [Parameter(Mandatory = $false)]
    [int]$MaxRestarts = 3,
    
    [Parameter(Mandatory = $false)]
    [int]$HealthCheckInterval = 30
)

# Configuration
$Script:Config = @{
    ComfyUIPath = "C:\AI\ComfyUI"
    RepoPath = "C:\Gitrepos\evavo-local-image-generator"
    ComfyUIURL = "http://127.0.0.1:8188"
    LogDir = "C:\Gitrepos\evavo-logs"
    StateFile = "C:\Gitrepos\evavo-state\automation.json"
    MaxStartupWait = 120
    HealthCheckInterval = $HealthCheckInterval
    MaxRestarts = $MaxRestarts
}

$Script:State = @{
    ComfyUIRunning = $false
    ComfyUIPID = $null
    StartCount = 0
    LastHealthCheck = $null
    GenerationsSinceStart = 0
    Uptime = 0
    Errors = @()
}

# ==================== LOGGING ====================

function Initialize-Logging {
    if (-not (Test-Path $Script:Config.LogDir)) {
        New-Item -ItemType Directory -Path $Script:Config.LogDir -Force | Out-Null
    }
    
    if (-not (Test-Path "C:\Gitrepos\evavo-state")) {
        New-Item -ItemType Directory -Path "C:\Gitrepos\evavo-state" -Force | Out-Null
    }
}

function Write-Status {
    param(
        [string]$Message,
        [ValidateSet("INFO", "SUCCESS", "ERROR", "WARNING", "DEBUG")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "DEBUG" { "Gray" }
        default { "White" }
    }

    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage -ForegroundColor $color
    
    # Append to log file
    $logFile = Join-Path $Script:Config.LogDir "automation-$(Get-Date -Format 'yyyyMMdd').log"
    Add-Content -Path $logFile -Value $logMessage -ErrorAction SilentlyContinue
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

# ==================== STATE MANAGEMENT ====================

function Save-State {
    $stateData = @{
        Timestamp = (Get-Date).ToString("o")
        ComfyUIRunning = $Script:State.ComfyUIRunning
        ComfyUIPID = $Script:State.ComfyUIPID
        StartCount = $Script:State.StartCount
        GenerationsSinceStart = $Script:State.GenerationsSinceStart
        Uptime = $Script:State.Uptime
        LastHealthCheck = $Script:State.LastHealthCheck
    }
    
    $stateData | ConvertTo-Json | Set-Content $Script:Config.StateFile -ErrorAction SilentlyContinue
}

function Restore-State {
    if (Test-Path $Script:Config.StateFile) {
        try {
            $stateData = Get-Content $Script:Config.StateFile | ConvertFrom-Json
            $Script:State.StartCount = $stateData.StartCount
            $Script:State.GenerationsSinceStart = $stateData.GenerationsSinceStart
        } catch {
            Write-Status "Could not restore state, starting fresh" "WARNING"
        }
    }
}

# ==================== COMFYUI MANAGEMENT ====================

function Test-ComfyUIHealth {
    try {
        $response = Invoke-WebRequest -Uri "$($Script:Config.ComfyUIURL)/system_stats" `
            -TimeoutSec 5 `
            -ErrorAction Stop
        
        if ($response.StatusCode -eq 200) {
            $Script:State.LastHealthCheck = (Get-Date)
            return $true
        }
    } catch {
        return $false
    }
}

function Start-ComfyUI {
    Write-Status "Checking if ComfyUI is already running..." "INFO"
    
    # Check if already running
    if (Test-ComfyUIHealth) {
        Write-Status "✓ ComfyUI already running" "SUCCESS"
        $Script:State.ComfyUIRunning = $true
        return $true
    }
    
    # Kill any orphaned processes
    Get-Process python -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*main.py*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    
    Write-Status "Starting ComfyUI..." "INFO"
    
    try {
        $process = Start-Process `
            -FilePath "python" `
            -ArgumentList "main.py" `
            -WorkingDirectory $Script:Config.ComfyUIPath `
            -WindowStyle Normal `
            -PassThru
        
        $Script:State.ComfyUIPID = $process.Id
        $Script:State.ComfyUIRunning = $true
        $Script:State.StartCount++
        
        Write-Status "✓ ComfyUI started (PID: $($process.Id))" "SUCCESS"
        return $true
        
    } catch {
        Write-Status "Failed to start ComfyUI: $_" "ERROR"
        $Script:State.ComfyUIRunning = $false
        return $false
    }
}

function Wait-ForComfyUIReady {
    $startTime = Get-Date
    $maxWait = $Script:Config.MaxStartupWait
    $attempt = 0

    Write-Status "Waiting for ComfyUI to be ready..." "INFO"
    
    while ((Get-Date) - $startTime -lt [TimeSpan]::FromSeconds($maxWait)) {
        $attempt++
        
        if (Test-ComfyUIHealth) {
            Write-Status "✓ ComfyUI is ready!" "SUCCESS"
            return $true
        }
        
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        Write-Status "  Attempt $attempt - Waiting ({0:F1}s)..." -f $elapsed "DEBUG"
        Start-Sleep -Seconds 3
    }

    Write-Status "✗ ComfyUI startup timeout after $maxWait seconds" "ERROR"
    return $false
}

function Ensure-ComfyUIRunning {
    if (Test-ComfyUIHealth) {
        return $true
    }
    
    Write-Status "ComfyUI health check failed, restarting..." "WARNING"
    
    if ($Script:State.StartCount -ge $Script:Config.MaxRestarts) {
        Write-Status "Max restart attempts ($($Script:Config.MaxRestarts)) exceeded" "ERROR"
        return $false
    }
    
    if (-not (Start-ComfyUI)) {
        return $false
    }
    
    return (Wait-ForComfyUIReady)
}

# ==================== GENERATION MANAGEMENT ====================

function Run-Generation {
    Write-Banner "RUNNING AUTONOMOUS GENERATION"
    
    if (-not (Ensure-ComfyUIRunning)) {
        Write-Status "Cannot start generation - ComfyUI not available" "ERROR"
        return $false
    }
    
    try {
        Push-Location $Script:Config.RepoPath
        
        $generationLog = Join-Path $Script:Config.LogDir "generation-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
        
        Write-Status "Starting autonomous generation..." "INFO"
        
        & python run_autonomous.py *>&1 | Tee-Object -FilePath $generationLog
        
        $exitCode = $LASTEXITCODE
        Pop-Location
        
        if ($exitCode -eq 0) {
            $Script:State.GenerationsSinceStart++
            Write-Status "✓ Generation completed successfully" "SUCCESS"
            return $true
        } else {
            Write-Status "✗ Generation failed (exit code: $exitCode)" "ERROR"
            $Script:State.Errors += "Generation failed at $(Get-Date)"
            return $false
        }
    }
    catch {
        Write-Status "Error running generation: $_" "ERROR"
        $Script:State.Errors += "Exception: $_"
        return $false
    }
}

# ==================== MONITORING ====================

function Monitor-System {
    Write-Banner "SYSTEM MONITORING ACTIVE"
    
    Restore-State
    $startTime = Get-Date
    
    while ($true) {
        $Script:State.Uptime = ((Get-Date) - $startTime).TotalSeconds
        
        # Health check
        if (-not (Ensure-ComfyUIRunning)) {
            Write-Status "⚠ ComfyUI recovery failed, system degraded" "ERROR"
            Start-Sleep -Seconds $Script:Config.HealthCheckInterval
            continue
        }
        
        # Log status
        Write-Status "System healthy - PID: $($Script:State.ComfyUIPID), Generations: $($Script:State.GenerationsSinceStart), Uptime: $($Script:State.Uptime.ToString('F0'))s" "INFO"
        
        # Save state
        Save-State
        
        # Wait for next check
        Start-Sleep -Seconds $Script:Config.HealthCheckInterval
    }
}

function Show-Status {
    Write-Banner "EVAVO SYSTEM STATUS"
    
    Restore-State
    
    Write-Host "Status Information:"
    Write-Host "  ComfyUI URL: $($Script:Config.ComfyUIURL)"
    Write-Host "  Repository: $($Script:Config.RepoPath)"
    Write-Host "  Log Directory: $($Script:Config.LogDir)"
    Write-Host ""
    
    if (Test-ComfyUIHealth) {
        Write-Status "✓ ComfyUI: Running" "SUCCESS"
    } else {
        Write-Status "✗ ComfyUI: Not running" "ERROR"
    }
    
    Write-Host ""
    Write-Host "Statistics:"
    Write-Host "  Total Starts: $($Script:State.StartCount)"
    Write-Host "  Generations: $($Script:State.GenerationsSinceStart)"
    Write-Host "  Last Health Check: $($Script:State.LastHealthCheck)"
    Write-Host ""
    
    if ($Script:State.Errors.Count -gt 0) {
        Write-Host "Recent Errors:"
        $Script:State.Errors[-5..-1] | ForEach-Object {
            Write-Status "  $_" "ERROR"
        }
    }
}

# ==================== SCHEDULED OPERATION ====================

function Setup-ScheduledTask {
    Write-Banner "SETTING UP SCHEDULED AUTOMATION"
    
    $taskName = "EVAVO-MasterAutomation"
    $scriptPath = "$($Script:Config.RepoPath)\MASTER-AUTOMATION-CONTROLLER.ps1"
    
    # Remove existing task
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Status "Removing existing scheduled task..." "INFO"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    
    # Create new task
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode Full"
    
    $trigger = New-ScheduledTaskTrigger -AtStartup
    
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -DontStopIfGoingOnBatteries
    
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -RunLevel Highest `
        -ErrorAction Stop
    
    Write-Status "✓ Scheduled task created: $taskName" "SUCCESS"
    Write-Status "  Runs: On system startup" "INFO"
}

# ==================== MAIN EXECUTION ====================

function Main {
    Initialize-Logging
    Write-Banner "EVAVO MASTER AUTOMATION CONTROLLER v2.0.0"
    
    Write-Status "Mode: $Mode" "INFO"
    Write-Status "Max Restarts: $($Script:Config.MaxRestarts)" "INFO"
    Write-Status "Health Check Interval: $($Script:Config.HealthCheckInterval)s" "INFO"
    
    switch ($Mode) {
        "Full" {
            # Full autonomous mode with generation
            Restore-State
            
            if (-not (Start-ComfyUI)) {
                Write-Status "Failed to start ComfyUI" "ERROR"
                exit 1
            }
            
            Start-Sleep -Seconds 3
            
            if (-not (Wait-ForComfyUIReady)) {
                Write-Status "ComfyUI failed to initialize" "ERROR"
                exit 1
            }
            
            Start-Sleep -Seconds 2
            
            $success = Run-Generation
            
            Save-State
            
            if ($success) {
                Write-Status "✓ Autonomous cycle completed successfully" "SUCCESS"
                exit 0
            } else {
                Write-Status "✗ Autonomous cycle completed with errors" "ERROR"
                exit 1
            }
        }
        
        "Monitor" {
            # Continuous monitoring mode
            Restore-State
            
            if (-not (Start-ComfyUI)) {
                exit 1
            }
            
            Monitor-System
        }
        
        "Service" {
            # Install as Windows service via scheduled task
            Setup-ScheduledTask
            Write-Status "✓ Automation service configured" "SUCCESS"
        }
        
        "Test" {
            # Test mode - just verify everything is working
            Restore-State
            
            Write-Banner "SYSTEM TEST"
            
            Write-Status "Testing ComfyUI connectivity..." "INFO"
            if (Test-ComfyUIHealth) {
                Write-Status "✓ ComfyUI is responding" "SUCCESS"
            } else {
                Write-Status "⚠ ComfyUI not responding (will auto-start)" "WARNING"
                
                if (Start-ComfyUI) {
                    Start-Sleep -Seconds 3
                    if (Wait-ForComfyUIReady) {
                        Write-Status "✓ ComfyUI started successfully" "SUCCESS"
                    } else {
                        Write-Status "✗ ComfyUI failed to initialize" "ERROR"
                    }
                }
            }
            
            Write-Status "Testing generation pipeline..." "INFO"
            if (Test-Path "$($Script:Config.RepoPath)\run_autonomous.py") {
                Write-Status "✓ Generation script found" "SUCCESS"
            } else {
                Write-Status "✗ Generation script missing" "ERROR"
            }
            
            Show-Status
        }
        
        "Status" {
            Show-Status
        }
    }
}

# Run main
try {
    Main
} catch {
    Write-Status "Critical error: $_" "ERROR"
    exit 1
}
