# EVAVO Local Image Generator - Quick Reference

## Preferred commands

```powershell
# Start and verify the managed local service
python evavo.py start

# Check health
python evavo.py status

# Generate a batch
python evavo.py generate --prompts "landscape" "portrait" "abstract" --project demo

# Built-in example batch
python evavo.py generate --examples

# Task history and statistics
python evavo.py tasks --limit 20
python evavo.py stats

# Run end-to-end operational validation
python evavo.py test

# Stop the managed service
python evavo.py stop
```

## Direct utility commands

| Operation | Command |
|---|---|
| One-shot health | `python monitor-evavo.py` |
| Health JSON | `python monitor-evavo.py --json` |
| Continuous health | `python monitor-evavo.py --continuous --interval 10` |
| Batch examples | `python generate-batch.py --examples` |
| Batch JSON | `python generate-batch.py --prompts "one" "two" --json` |
| Set concurrency | `python generate-batch.py --examples --concurrency 4` |
| List tasks | `python task-tracker.py list --limit 20` |
| Task stats | `python task-tracker.py stats` |
| Filter project | `python task-tracker.py list --project demo` |
| Mark completed | `python task-tracker.py update <TASK_ID> completed` |
| Clear history | `python task-tracker.py clear --yes` |
| Wrapper health | `python evavo-wrapper.py health_check "{}"` |
| Windows startup | `START-EVAVO-SERVICES.bat` |

## Runtime files

| Component | File | Purpose |
|---|---|---|
| Unified controller | `evavo.py` | Start/stop/status/generate/tasks/test |
| Shared operations | `evavo_operations.py` | HTTP contract, health validation, durable task history |
| Mock service | `mock-comfyui-server.py` | Local ComfyUI-compatible queue API on port 8188 |
| Wrapper | `evavo-wrapper.py` | Stable machine-readable generation/health CLI |
| Batch | `generate-batch.py` | Bounded concurrent queueing + tracking |
| Monitor | `monitor-evavo.py` | Service and wrapper health |
| Tracker | `task-tracker.py` | Task history CLI |
| Windows launcher | `START-EVAVO-SERVICES.bat` | Safe Windows startup/readiness loop |
| Integration tests | `test-operations.py` | End-to-end operational validation |

## HTTP endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `http://127.0.0.1:8188/system` | GET | Identity/readiness contract |
| `http://127.0.0.1:8188/api/status` | GET | Queue/service status |
| `http://127.0.0.1:8188/api/prompt` | POST | Queue an image-generation task |

Healthy `/system` responses identify:

```json
{
  "service": "evavo-local-image-generator",
  "protocol_version": 1,
  "status": "ready"
}
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | General or partial failure |
| `2` | Invalid argument/configuration/prerequisite |
| `3` | Service/wrapper unavailable or degraded |
| `4` | Task not found |
| `5` | Windows port conflict with a non-EVAVO process |

## Local state

```text
.evavo/operations-service.json   managed service PID/state
.evavo/mock-service.log          managed service log
task_history.json                persistent generation history
task_history.json.lock           inter-process history lock
```

Override task history location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\task_history.json"
```

Override service endpoint:

```powershell
$env:COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
```

## Common failures

```powershell
# Port owner
Get-NetTCPConnection -LocalPort 8188 -State Listen

# Detailed health
python monitor-evavo.py --json

# Full operational validation
python test-operations.py
```

Do **not** broadly run `taskkill /IM python.exe`; the startup tooling is designed to avoid killing unrelated Python processes.

See `OPERATIONS-GUIDE.md` for deployment, recovery, storage URI, security and troubleshooting details.
