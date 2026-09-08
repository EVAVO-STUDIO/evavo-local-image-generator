# EVAVO Local Image Generator - Quick Reference

## One-Liners

```bash
# Start everything
START-EVAVO-SERVICES.bat && python generate-batch.py --examples

# Monitor continuously
python monitor-evavo.py --continuous

# View task history
python task-tracker.py list

# Get stats
python task-tracker.py stats

# Custom batch
python generate-batch.py --prompts "landscape" "portrait" "abstract"
```

## File Locations

| Component | Location | Purpose |
|-----------|----------|---------|
| Mock Server | mock-comfyui-server.py | HTTP API endpoint (port 8188) |
| EVAVO Wrapper | evavo-wrapper.py | Main generation entry point |
| Batch Tool | generate-batch.py | Queue multiple tasks |
| Monitor | monitor-evavo.py | Health status checks |
| Task Log | task-tracker.py | History & statistics |
| Startup | START-EVAVO-SERVICES.bat | Windows service launcher |

## Common Tasks

**Generate 5 images from examples**
```bash
python generate-batch.py --examples
```

**Generate images with custom prompts**
```bash
python generate-batch.py --prompts "prompt1" "prompt2" "prompt3"
```

**Monitor system health (continuous)**
```bash
python monitor-evavo.py --continuous
```

**Check system health (one-time)**
```bash
python monitor-evavo.py
```

**View last 20 tasks**
```bash
python task-tracker.py list
```

**View last 50 tasks**
```bash
python task-tracker.py list --limit 50
```

**Get generation statistics**
```bash
python task-tracker.py stats
```

**Clear task history**
```bash
python task-tracker.py clear
```

## Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `http://127.0.0.1:8188/system` | Health check | JSON status |
| `http://127.0.0.1:8188/api/status` | System info | JSON data |
| `http://127.0.0.1:8188/api/prompt` | Queue task | Task confirmation |

## Exit Codes

```
0  - Success
1  - General error
127 - Command not found
255 - Port unavailable
```

## Storage

Generated images stored in: `bee://primary/EVAVO/ImageGeneration/outputs/`

## Support

- Check OPERATIONS-GUIDE.md for detailed workflows
- Review DEPLOYMENT-ACTIVE.md for technical architecture
- Use monitor-evavo.py to diagnose issues
