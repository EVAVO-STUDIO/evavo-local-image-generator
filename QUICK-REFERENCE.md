# EVAVO Local Image Generator - Quick Reference

## Preferred commands

```powershell
# Diagnose Python, files, Git state and service health
python evavo.py doctor

# First-class automated workflow: sync main -> doctor -> tests -> start -> status
python evavo.py bootstrap

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

## Windows workstation update

If the checkout predates `evavo.py`, fast-forward it once:

```powershell
git pull --ff-only origin main
```

After that, either use the Python controller:

```powershell
python evavo.py bootstrap
```

or the PowerShell wrapper:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Both paths refuse destructive Git updates. `bootstrap` uses `git pull --ff-only` and stops when local changes would need to be overwritten.

## Direct utility commands

| Operation | Command |
|---|---|
| Doctor JSON | `python evavo.py doctor --json` |
| Sync main | `python evavo.py sync` |
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
| Unified controller | `evavo.py` | Doctor/sync/bootstrap/start/stop/status/generate/tasks/test |
| Shared operations | `evavo_operations.py` | HTTP contract, health validation, durable task history |
| Mock service | `mock-comfyui-server.py` | Local ComfyUI-compatible queue API |
| Wrapper | `evavo-wrapper.py` | Stable machine-readable generation/health CLI |
| Batch | `generate-batch.py` | Bounded concurrent queueing + tracking |
| Monitor | `monitor-evavo.py` | Service and wrapper health |
| Tracker | `task-tracker.py` | Task history CLI |
| Windows launcher | `START-EVAVO-SERVICES.bat` | Thin launcher around `evavo.py doctor/start/status` |
| Windows updater | `UPDATE-AND-VERIFY-EVAVO.ps1` | Safe update + bootstrap |
| Integration tests | `test-operations.py` | End-to-end operational validation, including controller lifecycle |

## HTTP endpoints

Default endpoint: `http://127.0.0.1:8188`

| Endpoint | Method | Purpose |
|---|---|---|
| `/system` | GET | Identity/readiness contract |
| `/api/status` | GET | Queue/service status |
| `/api/prompt` | POST | Queue an image-generation task |

Healthy `/system` responses identify:

```json
{
  "service": "evavo-local-image-generator",
  "protocol_version": 1,
  "status": "ready"
}
```

The Python controller also supports isolated loopback ports for testing, for example:

```powershell
python evavo.py start --endpoint http://127.0.0.1:18190
python evavo.py status --endpoint http://127.0.0.1:18190
python evavo.py stop
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | General or partial failure |
| `2` | Invalid argument/configuration/prerequisite |
| `3` | Service/wrapper unavailable, degraded, or startup timeout |
| `4` | Task not found |

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
# Diagnose environment and stale checkout issues
python evavo.py doctor

# Detailed health
python monitor-evavo.py --json

# Full operational validation
python evavo.py test

# Managed service log
Get-Content .\.evavo\mock-service.log -Tail 100
```

Python 3.10+ already includes `asyncio`. Do not install the PyPI `asyncio` package for this repository. `evavo.py doctor` warns if `asyncio` resolves from `site-packages` instead of the standard library.

Do **not** broadly run `taskkill /IM python.exe`; the process tooling is designed to avoid killing unrelated Python processes.

See `OPERATIONS-GUIDE.md` for deployment, recovery, storage URI, security and troubleshooting details.
