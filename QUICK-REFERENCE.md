# EVAVO Local Image Generator - Quick Reference

## Canonical Windows setup

After cloning or after an old checkout has been updated once, use:

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

That single script now:

1. fast-forwards `main` without overwriting local changes;
2. installs/updates dependencies, including `mcp[cli]>=2,<3`;
3. runs operational integration tests;
4. negotiates MCP through in-process, stdio and Streamable HTTP clients;
5. bootstraps/selects the EVAVO generation backend;
6. installs/updates Claude Desktop stdio MCP configuration;
7. installs and starts per-user HTTP MCP autostart on `127.0.0.1:8765`;
8. runs `agent-doctor.py --repair`;
9. performs a final backend status check.

Skip automatic Claude/HTTP configuration only when troubleshooting:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
```

## Agent readiness

Human-readable diagnosis:

```powershell
python agent-doctor.py
```

Machine-readable diagnosis with safe backend repair:

```powershell
python agent-doctor.py --repair --json
```

Checks include Python, MCP SDK, local ComfyUI discovery, native backend health, checkpoint availability, output-directory writability, Claude configuration, HTTP MCP listener, HTTP autostart and negotiated MCP protocol tests.

## Claude Desktop

The canonical updater configures Claude automatically. To install/update only Claude:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses stdio MCP and spawns EVAVO on demand. Restart Claude Desktop after changing its MCP configuration.

Underlying command:

```powershell
python -m evavo_local_image_generator.mcp_server --transport stdio
```

## ChatGPT/local MCP clients

Loopback Streamable HTTP endpoint:

```text
http://127.0.0.1:8765/mcp
```

Start manually:

```powershell
.\START-AGENT-MCP.ps1
```

Install per-user Windows-login autostart and start it immediately:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

Remove the login autostart:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1 -Uninstall
```

The listener remains loopback-only. Do not publicly expose it merely to make a cloud client reach workstation localhost.

## MCP tools

```text
ensure_backend
discover_backends
health_check
list_checkpoints
generate_image
generation_status
collect_generation
stop_managed_backend
```

`generate_image` defaults to automatically ensuring native ComfyUI is running, waiting for completion and returning downloaded local file paths.

## Real image generation

Queue only:

```powershell
python evavo.py generate --prompts "PS1 horror corridor" --project ps1
```

Render, wait and download the actual image:

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
| Diagnose operations | `python evavo.py doctor` |
| Diagnose agents | `python agent-doctor.py --repair` |
| Sync `main` | `python evavo.py sync` |
| Full bootstrap | `python evavo.py bootstrap` |
| Start/select backend | `python evavo.py start` |
| Backend status | `python evavo.py status` |
| Queue batch | `python evavo.py generate --prompts "one" "two" --project demo` |
| Tasks | `python evavo.py tasks --limit 20` |
| Statistics | `python evavo.py stats` |
| Operational tests | `python evavo.py test` |
| Agent/MCP tests | `python test-agent-integration.py` |
| Stop EVAVO-owned fallback | `python evavo.py stop` |

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

## Backend behavior

Default ComfyUI endpoint:

```text
http://127.0.0.1:8188
```

Agent generation requires a **real native ComfyUI**. EVAVO can discover and start source or Windows-portable installations automatically. Set a non-standard install explicitly with:

```powershell
$env:EVAVO_COMFYUI_HOME = "D:\AI\ComfyUI"
```

Native routes used by EVAVO:

```text
GET  /system_stats
GET  /object_info/CheckpointLoaderSimple
POST /prompt
GET  /history/{prompt_id}
GET  /view?filename=...&subfolder=...&type=...
```

The deterministic EVAVO mock is used for operational validation/fallback only and is explicitly rejected by the agent lifecycle manager as a native renderer.

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
{{PROMPT}}
{{NEGATIVE_PROMPT}}
{{WIDTH}}
{{HEIGHT}}
{{STEPS}}
{{CFG}}
{{SEED}}
{{CHECKPOINT}}
{{FILENAME_PREFIX}}
```

## State/output files

```text
.evavo/operations-service.json       EVAVO-owned fallback PID/state
.evavo/mock-service.log              fallback log
.evavo/native-comfyui-service.json   native ComfyUI PID/state when EVAVO started it
.evavo/native-comfyui.log            native ComfyUI startup log
.evavo/outputs/                      default downloaded images
task_history.json                    generation history
task_history.json.lock               inter-process lock
```

Windows HTTP MCP login launcher:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EVAVO-Agent-MCP.cmd
```

## Recovery

```powershell
python agent-doctor.py --repair
python evavo.py doctor
python monitor-evavo.py --json
python test-agent-integration.py
python evavo.py test
Get-Content .\.evavo\native-comfyui.log -Tail 100
Get-Content .\.evavo\mock-service.log -Tail 100
```

Python 3.10+ already includes `asyncio`. Do **not** install the separate PyPI `asyncio` package for this repository.

Do **not** use broad `taskkill /IM python.exe`; EVAVO only stops processes it records as its own.
