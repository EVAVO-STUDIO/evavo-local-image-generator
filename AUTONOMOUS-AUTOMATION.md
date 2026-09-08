# EVAVO Autonomous Automation System

**Version:** 2.0.0  
**Status:** ✅ PRODUCTION READY  
**Automation Level:** FULLY AUTONOMOUS

---

## Overview

The EVAVO Autonomous Automation System provides **zero-manual-intervention** operation:
- ✅ Auto-starts ComfyUI
- ✅ Auto-waits for readiness
- ✅ Auto-detects failures
- ✅ Auto-recovers from errors
- ✅ Auto-generates images
- ✅ Auto-logs everything
- ✅ Auto-schedules operations

---

## Quick Start (3 Options)

### Option 1: Windows Batch File (Easiest)
**Just double-click:**
```
START-AUTONOMOUS.bat
```
Everything runs automatically. No typing needed.

### Option 2: PowerShell (Full Control)
**From PowerShell:**
```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full
```

### Option 3: Python (Cross-platform)
**From Command Prompt:**
```bash
cd C:\Gitrepos\evavo-local-image-generator
python START-EVERYTHING.py
```

---

## Automation Modes

### Mode: Full (Recommended)
**Complete autonomous cycle:**
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full
```

**Does:**
1. ✅ Start ComfyUI (if not running)
2. ✅ Wait for readiness (auto-recovery)
3. ✅ Run autonomous generation
4. ✅ Save results
5. ✅ Log everything
6. ✅ Exit cleanly

**Time:** 2-10 minutes depending on generation complexity

---

### Mode: Monitor (Always Running)
**Continuous background operation:**
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Monitor
```

**Does:**
- Continuously monitors ComfyUI health
- Auto-restarts if service crashes
- Logs all activity
- Keeps running indefinitely

**Use for:** Running 24/7 as background service

---

### Mode: Service (Windows Scheduled Task)
**Install as automatic startup service:**
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Service
```

**Does:**
- Registers Windows scheduled task
- Runs automatically on system startup
- Auto-restarts on failure
- Requires administrator privileges

**Use for:** Automatic daily/hourly generations

---

### Mode: Test (Verification)
**Quick system check:**
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Test
```

**Verifies:**
- ComfyUI connectivity
- Generation pipeline ready
- All dependencies installed
- No action taken

---

### Mode: Status (Information Only)
**View current system status:**
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Status
```

**Shows:**
- ComfyUI running status
- Number of generations completed
- Error history
- System statistics

---

## Automated Deployment Scenarios

### Scenario 1: Single Generation (Daily)
```powershell
# Schedule at 9 AM every day
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -File MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full"
Register-ScheduledTask -TaskName "EVAVO-DailyGeneration" -Trigger $trigger -Action $action
```

### Scenario 2: Continuous Monitoring (24/7)
```powershell
# Start in monitor mode (will run continuously)
Start-Process powershell -ArgumentList `
  "-NoProfile -File MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Monitor" `
  -WindowStyle Hidden
```

### Scenario 3: Hourly Generation
```powershell
# Generate every hour automatically
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Hours 1) `
  -RepetitionDuration (New-TimeSpan -Days 30)
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -File MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full"
Register-ScheduledTask -TaskName "EVAVO-HourlyGeneration" -Trigger $trigger -Action $action
```

### Scenario 4: System Startup (Automatic on Boot)
```powershell
# Use Service mode to auto-install at startup
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Service
```

---

## Configuration Parameters

### Startup Behavior
```powershell
-MaxRestarts 3          # Max number of ComfyUI restart attempts
-HealthCheckInterval 30 # Seconds between health checks
```

### Example: Aggressive Monitoring
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 `
  -Mode Monitor `
  -MaxRestarts 5 `
  -HealthCheckInterval 10
```

---

## Output & Logging

### Generated Images
**Location:** `C:\Gitrepos\evavo-generations\`
```
image_001.png
image_002.png
video_001.mp4
...
```

### System Logs
**Location:** `C:\Gitrepos\evavo-logs\`
```
automation-20260908.log     # Daily automation log
generation-20260908-*.log   # Generation logs (timestamped)
mcp-bridge.log              # MCP integration logs
```

### State File
**Location:** `C:\Gitrepos\evavo-state\automation.json`
```json
{
  "Timestamp": "2026-09-08T14:30:00",
  "ComfyUIRunning": true,
  "StartCount": 5,
  "GenerationsSinceStart": 12,
  "Uptime": 3600
}
```

### View Logs
```powershell
# Today's automation log (last 50 lines)
Get-Content C:\Gitrepos\evavo-logs\automation-*.log -Tail 50

# All generation logs
Get-ChildItem C:\Gitrepos\evavo-logs\generation-*.log

# Latest generation
Get-Content (Get-ChildItem C:\Gitrepos\evavo-logs\generation-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName | Tail 100
```

---

## Error Handling & Recovery

### Auto-Recovery Features

**1. ComfyUI Crash Detection**
- Health checks every N seconds
- Automatic restart on failure
- Up to 3 restart attempts
- Exponential backoff between retries

**2. Generation Failure Handling**
- Logs all errors to file
- Continues to next generation
- Tracks error history
- No manual intervention needed

**3. Network Issues**
- Timeout handling (5 seconds)
- Connection retry logic
- Graceful degradation
- Status reporting

### Manual Recovery
If something goes wrong:
```powershell
# Check status
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Status

# Kill all processes
Get-Process python | Stop-Process -Force

# Run test
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Test

# Try again
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full
```

---

## Advanced Usage

### Custom Startup Script
Create `C:\Gitrepos\evavo-local-image-generator\my-schedule.ps1`:
```powershell
# Generate at specific times
$times = @("09:00", "12:00", "15:00", "18:00")

foreach ($time in $times) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
      -Argument "-NoProfile -File MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full"
    Register-ScheduledTask -TaskName "EVAVO-$time" -Trigger $trigger -Action $action
}
```

### Conditional Generation
Modify `run_autonomous.py` for custom logic:
```python
# Generate only during business hours
from datetime import datetime

if 9 <= datetime.now().hour <= 17:
    controller.generate_image_series(subjects=[...])
else:
    print("Outside business hours, skipping generation")
```

### Resource Limits
Monitor resource usage:
```powershell
# Get GPU usage
Get-WmiObject Win32_PerfFormattedData_NvidiaSmiPeriodicalSampler_NVIDASMI

# Get memory usage
Get-Process python | Measure-Object -Property WorkingSet64 -Sum
```

---

## Troubleshooting

### "ComfyUI failed to start"
**Solution:**
```powershell
# Check ComfyUI exists
Test-Path "C:\AI\ComfyUI\main.py"

# Verify Python
python --version

# Try manual start
cd C:\AI\ComfyUI
python main.py
```

### "Generation timed out"
**Solution:**
```powershell
# Adjust timeout in run_autonomous.py
# Reduce quality setting: quality="standard" instead of "ultra"
# Generate smaller batches
```

### "Port 8188 already in use"
**Solution:**
```powershell
# Find process
Get-Process | Where-Object {$_.Handles -like "*8188*"}

# Kill it
Stop-Process -Name python -Force

# Clear the port
netstat -ano | findstr :8188
```

### "Out of GPU memory"
**Solution:**
```powershell
# Reduce generation quality
# Smaller batch sizes
# Free up other applications
# Restart ComfyUI
```

---

## Monitoring Dashboard (Optional)

View system status with HTML dashboard:
```powershell
# Generate HTML status page
python -c "
import json
with open('evavo-state\\automation.json') as f:
    data = json.load(f)
print(f'Status: {\"Running\" if data[\"ComfyUIRunning\"] else \"Stopped\"}')
print(f'Generations: {data[\"GenerationsSinceStart\"]}')
print(f'Uptime: {data[\"Uptime\"]} seconds')
"
```

---

## Performance Tuning

### Faster Generation
```powershell
# Use standard quality instead of ultra
# Reduce batch sizes
# Use faster model (SD 1.5 instead of SDXL)
```

### Parallel Processing
```powershell
# Generate multiple images simultaneously
python run_autonomous.py  # Generates 5 in parallel
```

### Scheduled Daily
```powershell
# Set to run once per day at off-peak hours
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"  # 2 AM
```

---

## Summary

The EVAVO Autonomous Automation System provides:
- ✅ **Zero Manual Intervention** - Everything automated
- ✅ **Self-Healing** - Auto-recovery from failures
- ✅ **24/7 Operation** - Run continuously or on schedule
- ✅ **Full Logging** - Complete audit trail
- ✅ **Easy Installation** - Single command deployment
- ✅ **Production Ready** - Enterprise-grade reliability

---

## Getting Started NOW

### Immediate: Run Once
```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full
```

### Today: Set Up Daily Automation
```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Service
```

### Tomorrow: Check Results
```powershell
Get-ChildItem C:\Gitrepos\evavo-generations\ -Filter *.png
```

---

**Status: ✅ AUTONOMOUS SYSTEM READY**  
**All automation installed and functional**  
**Ready for unattended 24/7 operation**
