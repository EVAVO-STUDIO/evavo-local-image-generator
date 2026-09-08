# EVAVO Local Image Generator - Quick Reference

## Preferred workflow

```powershell
cd C:\Gitrepos\evavo-local-image-generator
python evavo.py bootstrap
python evavo.py status
```

`bootstrap` syncs `main`, diagnoses the environment, runs integration tests, uses a healthy native ComfyUI if one is already running, otherwise starts the managed mock fallback, then verifies health.

## Real image generation

Queue only:

```powershell
python evavo.py generate --prompts "PS1 horror corridor" --project ps1
```

Render, wait, and download the actual image:

```powershell
python generate-batch.py --prompts "PS1 horror corridor" --project ps1 --wait
```

Custom output directory:

```powershell
python generate-batch.py --prompts "PS1 horror corridor" --project ps1 --wait --output-dir "C:\EVAVO\Generated"
```

Custom API workflow:

```powershell
python generate-batch.py --prompts "PS1 horror corridor" --workflow "C:\EVAVO\workflows\workflow-api.json" --wait
```

## Controller

| Operation | Command |
|---|---|
| Diagnose | `python evavo.py doctor` |
| Sync `main` | `python evavo.py sync` |
| Full bootstrap | `python evavo.py bootstrap` |
| Start/select backend | `python evavo.py start` |
| Backend status | `python evavo.py status` |
| Queue batch | `python evavo.py generate --prompts "one" "two" --project demo` |
| Tasks | `python evavo.py tasks --limit 20` |
| Statistics | `python evavo.py stats` |
| Integration tests | `python evavo.py test` |
| Stop EVAVO-owned mock | `python evavo.py stop` |

## Direct generation/wrapper operations

| Operation | Command |
|---|---|
| Queue batch | `python generate-batch.py --prompts "one" "two"` |
| Render + collect | `python generate-batch.py --prompts "one" --wait` |
| Machine JSON | `python generate-batch.py --prompts "one" --wait --json` |
| Wrapper health | `python evavo-wrapper.py health_check "{}"` |
| Task status | `python evavo-wrapper.py task_status "{\"task_id\":\"<id>\"}"` |
| Wait + collect existing task | `python evavo-wrapper.py wait_image "{\"task_id\":\"<id>\"}"` |
| Monitor | `python monitor-evavo.py --json` |

## Backend detection

Default endpoint: `http://127.0.0.1:8188`

The tools detect in this order:

1. EVAVO compatibility service via `/system`.
2. Native ComfyUI via `/system_stats`.
3. `evavo.py start` launches the mock fallback only when neither is available.

Native ComfyUI routes used by EVAVO:

```text
GET  /system_stats
GET  /object_info/CheckpointLoaderSimple
POST /prompt
GET  /history/{prompt_id}
GET  /view?filename=...&subfolder=...&type=...
```

EVAVO mock compatibility routes:

```text
GET  /system
GET  /api/status
POST /api/prompt
```

## Model/workflow configuration

Built-in workflow checkpoint override:

```powershell
$env:EVAVO_COMFYUI_CHECKPOINT = "your-model.safetensors"
```

Custom ComfyUI API workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\EVAVO\workflows\workflow-api.json"
```

Template placeholders:

```text
{{prompt}} {{negative_prompt}} {{checkpoint}}
{{width}} {{height}} {{steps}} {{cfg_scale}}
{{seed}} {{filename_prefix}}
```

## MCP agent integration

Install repository dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the MCP stdio server directly:

```powershell
python -m evavo_local_image_generator.mcp_server
```

Agent tools:

```text
health_check
list_checkpoints
generate_image
generation_status
collect_generation
```

The MCP server uses the current SDK v2 line and `generate_image` waits for the real output by default.

## State/output files

```text
.evavo/operations-service.json   EVAVO-owned mock PID/state
.evavo/mock-service.log          managed mock log
.evavo/outputs/                  default downloaded native images
task_history.json                generation history
task_history.json.lock           inter-process lock
```

## Important recovery commands

```powershell
python evavo.py doctor
python monitor-evavo.py --json
python evavo.py test
Get-Content .\.evavo\mock-service.log -Tail 100
```

Python 3.10+ already contains `asyncio`. Do **not** install the separate PyPI `asyncio` package for this repository.

Do **not** use broad `taskkill /IM python.exe`; EVAVO only stops processes it owns.
