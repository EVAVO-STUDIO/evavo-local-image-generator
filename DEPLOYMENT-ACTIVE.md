# EVAVO Local Image Generator — Active Deployment Architecture

This document describes the **current repository-backed production contract**. Live workstation state is always determined by the verifier/doctor/status commands, not by prose alone.

## Production architecture

```text
Claude stdio MCP / ChatGPT Secure MCP Tunnel / CLI / Python
                         |
                         v
                 EVAVO MCP / evavo.py
                         |
                         v
                 native ComfyUI only
                 /system_stats
                 /object_info
                 /prompt
                 /history/<id>
                 /view
                         |
                         v
             downloaded image outputs
                         |
                         v
              shared atomic task history
```

The deterministic EVAVO mock remains available for isolated operational tests, but it is **not a production renderer** and does not satisfy strict agent readiness or the optional HTTP gateway's healthy state.

## Native lifecycle

EVAVO can:

- reuse an already-running user-managed native ComfyUI;
- discover source and Windows-portable installs;
- provision the official source runtime when allowed and missing;
- use owner-configured checkpoint sources/shared model roots;
- start native ComfyUI in the background;
- validate the active workflow/model contract;
- restart only an identity-verified EVAVO-managed ComfyUI when EVAVO's effective shared-model config changes;
- never kill a user-managed or identity-mismatched process.

Preferred endpoint variable:

```text
COMFYUI_ENDPOINT
```

Legacy `EVAVO_COMFYUI_ENDPOINT` remains a fallback alias.

## Real rendering contract

```text
GET  /system_stats
GET  /object_info[/<node>]
POST /prompt
GET  /history/<prompt_id>
GET  /view
```

A native request uses ComfyUI's real `prompt_id` as the task ID. With waiting enabled, EVAVO polls history and downloads actual output files atomically.

## Workflow contract

The built-in workflow uses normal checkpoint txt2img nodes. Custom exported ComfyUI API workflows are supported and can be validated before queueing through `workflow_preflight`.

Uppercase and legacy lowercase placeholders are supported, including:

```text
{{PROMPT}} / {{prompt}}
{{NEGATIVE_PROMPT}} / {{negative_prompt}}
{{WIDTH}} / {{width}}
{{HEIGHT}} / {{height}}
{{STEPS}} / {{steps}}
{{CFG}} / {{CFG_SCALE}} / {{cfg}} / {{cfg_scale}}
{{SEED}} / {{seed}}
{{CHECKPOINT}} / {{checkpoint}}
{{FILENAME_PREFIX}} / {{filename_prefix}}
```

## Canonical Windows deployment

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Authoritative read-only verification:

```powershell
python evavo.py verify --full --require-powershell
```

Strict real-generation repair/readiness:

```powershell
python agent-doctor.py --repair --provision
```

Real image smoke test:

```powershell
python evavo.py generate --prompts "EVAVO deployment smoke test" --project smoke --wait
```

## Claude

Claude Desktop uses local stdio MCP. The updater configures it automatically, or use `INSTALL-CLAUDE-MCP.ps1`.

## ChatGPT

Cloud ChatGPT does not connect directly to workstation localhost. The supported architecture is:

```text
ChatGPT
  -> OpenAI Secure MCP Tunnel
  -> private workstation MCP listener
  -> EVAVO native image runtime
```

See `CHATGPT-TUNNEL.md`.

## Current MCP tools

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

## Optional HTTP gateway

`EVAVO-GATEWAY.py` is a loopback-only compatibility API. Image generation uses native ComfyUI. Historical video/audio/3D endpoints intentionally return HTTP `501` rather than fake queue IDs. CORS is off by default unless explicit origins are configured.

See `GATEWAY-INTEGRATION-GUIDE.md`.

## State and outputs

Primary current state lives below `.evavo/`, including native/mock manager state, generated extra-model-path config, gateway state, tunnel state/tools, and downloaded outputs. Shared task history uses `task_history.json` by default unless overridden.

## Verification boundary

A green deployment means the current verifier passes and the real active workflow is ready. A historical document, generated metadata file, or mock queue response is never treated as proof that real image rendering works.

Use `DEPLOYMENT-CHECKLIST.md`, `OPERATIONS-GUIDE.md`, `AGENT-INTEGRATION.md`, `CHATGPT-TUNNEL.md`, and `QUICK-REFERENCE.md` for current operations.
