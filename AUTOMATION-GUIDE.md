# EVAVO Automation Guide

This repository now has one verified production contract: **local image generation through native ComfyUI**. Historical multimodal startup instructions are retired.

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater safely fast-forwards `main`, installs dependencies, runs the authoritative verifier, repairs/provisions native ComfyUI when allowed, validates model/workflow readiness, configures Claude stdio MCP and the private loopback MCP listener, and configures the ChatGPT Secure MCP Tunnel when a valid OpenAI tunnel ID is already available.

## Real image generation

```powershell
python evavo.py generate --prompts "your prompt" --project demo --wait
```

Batch:

```powershell
python evavo.py generate --prompts "prompt one" "prompt two" --project batch --wait
```

Custom ComfyUI API workflow:

```powershell
python evavo.py generate --prompts "your prompt" --workflow "C:\workflows\api.json" --wait
```

No compatibility launcher generates samples unless prompts or `--examples` are explicitly supplied.

## Agent automation

### Claude Desktop

Claude uses local stdio MCP. The updater configures it automatically, or run:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after configuration changes.

### ChatGPT

Cloud ChatGPT does not connect directly to workstation localhost. EVAVO uses the official outbound OpenAI Secure MCP Tunnel while keeping MCP and ComfyUI private on loopback.

See:

```text
CHATGPT-TUNNEL.md
```

### Private local MCP

```text
http://127.0.0.1:8765/mcp
```

```powershell
.\START-AGENT-MCP.ps1
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

The listener is for local MCP clients, testing, and as the private target of the ChatGPT tunnel. Do not expose it directly to the public internet.

## Agent tools

Current MCP tools include:

```text
provision_backend
ensure_backend
health_check
discover_backends
list_checkpoints
model_inventory
workflow_preflight
generate_image
generate_batch
generation_status
collect_generation
read_output_image
task_history
task_statistics
stop_managed_backend
```

`generate_image` and `generate_batch` can automatically ensure/provision the native renderer when enabled, wait for completion, download outputs, persist task history, and return concrete file paths. `read_output_image` returns an authorized generated image as native MCP image content.

## Verification and repair

Authoritative repository verifier:

```powershell
python evavo.py verify --full --require-powershell
```

Strict real-generation readiness/repair:

```powershell
python agent-doctor.py --repair --provision
```

The deterministic EVAVO mock cannot satisfy the strict real-generation gate.

## Compatibility entry points

Historical filenames such as `EVAVO-AUTOMATION.py`, `run_autonomous.py`, `RUN-GENERATION.py`, `START-EVERYTHING.ps1`, and related batch files remain only as safe compatibility shims. They delegate to the canonical verifier/controller and do not maintain their own ComfyUI/Ollama/Kokoro lifecycle, copy to hardcoded BeeStation paths, create Scheduled Tasks, or fabricate multimodal outputs.

## What is not claimed by this repository

Video, audio, 3D model, particle, text, and dedicated PBR-texture generation are **not** part of the verified production runtime here. Use the appropriate dedicated EVAVO repository/tooling for those capabilities rather than treating placeholder metadata as generated assets.

## More detail

- `README.md` — current repository overview
- `AGENT-INTEGRATION.md` — Claude/MCP/runtime details
- `CHATGPT-TUNNEL.md` — real ChatGPT workstation connectivity
- `OPERATIONS-GUIDE.md` — operational behavior/recovery
- `QUICK-REFERENCE.md` — concise commands
