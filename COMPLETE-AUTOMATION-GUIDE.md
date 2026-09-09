# EVAVO Complete Automation Guide

This filename is retained for compatibility, but the current automation architecture is the same canonical native-image pipeline documented across the repository. Historical Ollama/Kokoro/multimodal/sample-generation instructions have been retired.

## One-command Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater:

1. requires branch `main` and a clean working tree;
2. safely fast-forwards from `origin/main`;
3. installs current dependencies;
4. runs `python evavo.py verify --full --require-powershell`;
5. bootstraps the verified native image backend;
6. configures Claude stdio MCP and private loopback HTTP MCP;
7. repairs/provisions native ComfyUI when allowed;
8. validates the active workflow/model contract;
9. configures the outbound ChatGPT Secure MCP Tunnel when a valid tunnel ID/runtime key are already available;
10. reports final backend/agent readiness.

## Authoritative verification

```powershell
python evavo.py verify --full --require-powershell
```

The verifier automatically discovers modern root/package test suites, compiles current Python sources in memory, parses supported PowerShell scripts, and rejects retired dangerous behavior in compatibility launchers.

Strict real-generation repair/readiness:

```powershell
python agent-doctor.py --repair --provision
```

The deterministic EVAVO mock cannot satisfy this gate.

## Generate real images

```powershell
python evavo.py generate --prompts "your prompt" --project demo --wait
```

Batch:

```powershell
python evavo.py generate --prompts "prompt one" "prompt two" --project batch --wait
```

Custom API-format workflow:

```powershell
python evavo.py generate --prompts "your prompt" --workflow "C:\workflows\api.json" --wait
```

Generation is request-driven. Historical compatibility launchers no longer generate sample assets merely because they were started.

## Claude

Claude Desktop uses local stdio MCP:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after its MCP config changes.

## ChatGPT

Cloud ChatGPT reaches the workstation through OpenAI Secure MCP Tunnel, not direct localhost exposure. See:

```text
CHATGPT-TUNNEL.md
```

The local MCP target remains private on loopback, normally:

```text
http://127.0.0.1:8765/mcp
```

## MCP tools

Current verified tool surface:

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

## Optional HTTP compatibility gateway

The gateway is **image-only in the verified production contract**. Video/audio/3D compatibility routes return HTTP `501` instead of fabricating queued work.

```powershell
.\START-GATEWAY.ps1
python gateway-smoke-test.py
```

See `GATEWAY-INTEGRATION-GUIDE.md`.

## Historical shortcuts

Old names such as `START-EVERYTHING.ps1`, `MASTER-AUTOMATION-CONTROLLER.ps1`, `EVAVO-AUTOMATION.py`, `run_autonomous.py`, `RUN-GENERATION.py`, and related `.bat`/`.sh` files remain only as safe compatibility shims. They delegate to the canonical verifier/controller/runtime and do not maintain separate service graphs.

## Scope

This repository verifies **image generation through native ComfyUI**. It does not claim production video, audio, 3D model, particle, general text, or dedicated PBR texture generation. Use the dedicated EVAVO repositories for those capabilities.

For current detail, use `README.md`, `CLAUDE.md`, `AGENT-INTEGRATION.md`, `AUTOMATION-GUIDE.md`, `OPERATIONS-GUIDE.md`, `DEPLOYMENT-CHECKLIST.md`, `CHATGPT-TUNNEL.md`, and `QUICK-REFERENCE.md`.
