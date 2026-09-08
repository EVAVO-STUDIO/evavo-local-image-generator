# EVAVO Complete Automation & Testing Guide

**Version:** 2.0.0  
**Updated:** 2026-09-08  
**Platform:** Windows + Cloud Integration

---

## Quick Start (One Command)

### Windows PowerShell
```powershell
# Start everything automatically (ComfyUI + Generation)
cd C:\Gitrepos\evavo-local-image-generator
.\START-EVERYTHING.ps1 -Mode Full
```

This will:
1. ✅ Start ComfyUI server
2. ✅ Wait for readiness (with health checks)
3. ✅ Verify all models are loaded
4. ✅ Run autonomous image generation
5. ✅ Log all operations

---

## Available Automation Scripts

### 1. **START-EVERYTHING.ps1** (Recommended)
**Full automated startup with monitoring**

```powershell
# Mode: Full (start + generate)
.\START-EVERYTHING.ps1 -Mode Full

# Mode: Start (just start ComfyUI and wait)
.\START-EVERYTHING.ps1 -Mode Start

# Mode: Monitor (keep ComfyUI running, no generation)
.\START-EVERYTHING.ps1 -Mode Monitor
```

**What it does:**
- Launches ComfyUI in background
- Health checks every 2 seconds (exponential backoff)
- Maximum 120-second startup timeout
- Verifies model loading
- Runs autonomous generation
- Logs all operations to file

---

### 2. **TEST-ALL-AI-SYSTEMS.py** (Verification)
**Comprehensive test suite for all AI systems**

```powershell
# From repository directory:
python TEST-ALL-AI-SYSTEMS.py
```

**Tests the following:**
- ✅ ComfyUI server health
- ✅ Available models (checkpoints, VAE, LoRAs, upscalers)
- ✅ Queue system
- ✅ Kokoro TTS (if running)
- ✅ Ollama LLM (if running)
- ✅ Image generation system
- ✅ MCP server integration
- ✅ Python dependencies
- ✅ System performance (CPU, RAM, disk)

**Output:**
- Console report with pass/fail status
- JSON results file: `ai-systems-test-results.json`

---

### 3. **run_autonomous.py** (Generation)
**Core autonomous image generation**

```powershell
python run_autonomous.py
```

**Generates:**
- System verification
- Single images
- Batch images (5 images)
- Videos
- Performance statistics

---

## Complete Testing Workflow

### Step 1: Verify System Health
```powershell
cd C:\Gitrepos\evavo-local-image-generator
python TEST-ALL-AI-SYSTEMS.py
```

**Expected output:**
```
[HH:MM:SS] [SUCCESS] ✓ ComfyUI is running
[HH:MM:SS] [SUCCESS] ✓ Model list retrieved
[HH:MM:SS] [SUCCESS] ✓ Queue system operational
...
[HH:MM:SS] [SUCCESS] ✓ All systems operational!
```

### Step 2: Start Everything
```powershell
.\START-EVERYTHING.ps1 -Mode Full
```

**Expected output:**
```
======================================================================
  EVAVO COMPLETE STARTUP & GENERATION SYSTEM
======================================================================

[HH:MM:SS] [INFO   ] Launching ComfyUI...
[HH:MM:SS] [SUCCESS] ✓ ComfyUI started (PID: XXXX)

======================================================================
  WAITING FOR COMFYUI READINESS
======================================================================

[HH:MM:SS] [INFO   ]   Attempt 1 - Waiting for ComfyUI (0.5s)...
[HH:MM:SS] [SUCCESS] ✓ ComfyUI is ready!

======================================================================
  STARTING AUTONOMOUS GENERATION
======================================================================

2026-09-08 HH:MM:SS,XXX - claude_control - INFO - Phase 1: System Verification
...
Generated: C:\Gitrepos\evavo-generations\image_001.png
```

### Step 3: Monitor Results
```powershell
# View generation logs
Get-Content C:\Gitrepos\evavo-logs\generation-*.log -Tail 50

# Check generated images
Get-ChildItem C:\Gitrepos\evavo-generations\ -Filter *.png | Measure-Object
```

---

## Troubleshooting

### Issue: "ComfyUI not found"
**Solution:**
- Ensure ComfyUI is installed at `C:\AI\ComfyUI`
- Run: `cd C:\AI\ComfyUI && python main.py`

### Issue: "Port 8188 already in use"
**Solution:**
```powershell
# Find and kill existing ComfyUI process
Get-Process python | Where-Object {$_.CommandLine -like "*main.py*"} | Stop-Process -Force

# Or change port in START-EVERYTHING.ps1
```

### Issue: Models not loading
**Solution:**
```powershell
# Check model directory
ls C:\AI\ComfyUI\models\checkpoints\

# Download models if missing
# Stable Diffusion v1.5: Download to models/checkpoints/
# SDXL: Download to models/checkpoints/
```

### Issue: Out of GPU memory
**Solution:**
- Reduce quality setting: `quality="standard"` instead of `"ultra"`
- Generate smaller batch sizes
- Clear ComfyUI cache: Delete `ComfyUI/web/output/*`

---

## AI Models & Services Overview

### ComfyUI (Image/Video Generation)
- **URL:** http://127.0.0.1:8188
- **Location:** C:\AI\ComfyUI
- **Status:** Check with START-EVERYTHING.ps1
- **Models:** Stable Diffusion, SDXL, ControlNet, etc.

### Kokoro (Text-to-Speech)
- **URL:** http://127.0.0.1:8000
- **Location:** C:\AI\Kokoro-FastAPI
- **Status:** Optional, monitored by TEST-ALL-AI-SYSTEMS.py

### Ollama (Local LLM)
- **URL:** http://127.0.0.1:11434
- **Models:** Check with `ollama list`
- **Status:** Optional, tested automatically

### EVAVO MCP Servers
- **Python Bridge:** mcp_bridge.py (generation controller)
- **Node.js Server:** image-generation-mcp.mjs (infrastructure interface)
- **Config:** evavo_mcp_config.json

---

## Performance Optimization Tips

### 1. Image Generation Quality Settings
```python
# Fast generation (2-5 minutes)
quality="standard"
style="photorealistic"

# High quality (5-10 minutes)
quality="high"
style="photorealistic"

# Ultra quality (10-20 minutes)
quality="ultra"
style="photorealistic"
```

### 2. Batch Processing
```python
# Sequential (slower, less memory)
results = controller.generate_image_series(
    subjects=[...],
    parallel=False
)

# Parallel (faster, more memory)
results = controller.generate_image_series(
    subjects=[...],
    parallel=True
)
```

### 3. System Resources
- **Recommended GPU:** NVIDIA RTX 3060+ (12GB VRAM)
- **Minimum RAM:** 16GB system RAM
- **Disk Space:** 50GB for models and outputs

---

## Automation Schedule

### Daily Generation
```powershell
# Schedule task to run generation daily at 10 AM
$trigger = New-ScheduledTaskTrigger -Daily -At 10:00AM
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -File C:\Gitrepos\evavo-local-image-generator\START-EVERYTHING.ps1 -Mode Full"
Register-ScheduledTask -TaskName "EVAVO-DailyGeneration" `
  -Trigger $trigger -Action $action
```

### Hourly System Check
```powershell
# Schedule system health check every hour
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 30)
$action = New-ScheduledTaskAction -Execute "python" `
  -Argument "TEST-ALL-AI-SYSTEMS.py" -WorkingDirectory "C:\Gitrepos\evavo-local-image-generator"
Register-ScheduledTask -TaskName "EVAVO-HourlyHealthCheck" `
  -Trigger $trigger -Action $action
```

---

## Advanced Configuration

### Custom Model Selection
Edit `run_autonomous.py`:
```python
# Change default model
MODEL = "sd-xl-fp16.safetensors"  # SDXL high quality
# or
MODEL = "sd-v1-5-fp16.safetensors"  # SD 1.5 fast
```

### Custom Timeout Settings
Edit `evavo_mcp_config.json`:
```json
{
  "capabilities": [
    {
      "id": "generate-image",
      "timeout": 600000,  // 10 minutes
      "retry": {
        "attempts": 5,
        "backoff": "exponential"
      }
    }
  ]
}
```

### Custom Output Directory
Edit `run_autonomous.py`:
```python
OUTPUT_DIR = "C:/MyCustomOutputPath/generations"
```

---

## Integration with Claude & ChatGPT

### Claude Integration
The MCP server allows Claude to:
- Request image generation
- Specify styles and quality
- Receive generation results
- Batch process images

### ChatGPT Integration
Via evavo-agent-infrastructure:
1. Register MCP server
2. Load task definitions from evavo.tasks.json
3. ChatGPT can request generation through infrastructure

---

## Support & Monitoring

### View Live Logs
```powershell
# MCP Bridge logs
Get-Content C:\Gitrepos\evavo-logs\mcp-bridge.log -Tail 100

# Generation logs
Get-Content C:\Gitrepos\evavo-logs\generation-*.log -Tail 50

# ComfyUI output
Get-Content C:\AI\ComfyUI\output.log -Tail 50
```

### Check Generated Files
```powershell
# List all generated images
Get-ChildItem C:\Gitrepos\evavo-generations\*.png | Sort-Object LastWriteTime -Descending

# Get statistics
(Get-ChildItem C:\Gitrepos\evavo-generations\*.png).Count
```

### Performance Monitoring
```powershell
# Run test suite and check results
python TEST-ALL-AI-SYSTEMS.py
Get-Content ai-systems-test-results.json | ConvertFrom-Json | Format-List
```

---

## Status Indicators

### ✅ All Systems Green
- ComfyUI responding to health checks
- All required models loaded
- Generation completing successfully
- No errors in logs

### ⚠️ Warnings
- Kokoro or Ollama not running (optional services)
- Some models missing (core models still present)
- Slow generation times (normal during first run)

### ❌ Critical Issues
- ComfyUI not responding
- Essential models missing
- GPU out of memory
- Python dependencies missing

---

## Next Steps

1. **Run diagnostic:** `python TEST-ALL-AI-SYSTEMS.py`
2. **Start system:** `.\START-EVERYTHING.ps1 -Mode Full`
3. **Monitor results:** Check C:\Gitrepos\evavo-generations\
4. **Optimize:** Adjust quality/batch settings as needed
5. **Schedule:** Set up automation tasks for regular use

---

**Ready to generate! Run:** `.\START-EVERYTHING.ps1 -Mode Full`

