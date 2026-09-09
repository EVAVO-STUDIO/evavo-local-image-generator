# EVAVO Local Image Generator

A Windows-first local image-generation control plane for **native ComfyUI**, with one operational contract shared by CLI automation, Claude Desktop and ChatGPT.

The deterministic EVAVO mock is test infrastructure, not a production renderer.

## Production ownership

This repository owns and verifies **image generation**.

Owned path:

```text
agent / CLI
  -> EVAVO lifecycle + policy
  -> native ComfyUI
  -> /prompt
  -> /history/<prompt_id>
  -> /view
  -> atomic local output
  -> shared task history
```

The optional loopback HTTP gateway may delegate video/audio/3D work to separately governed sibling EVAVO Studio providers. Those delegated routes are not MCP/package-owned generation capabilities of this repository.

## What works

- native ComfyUI discovery, health and safe lifecycle management;
- source and Windows-portable ComfyUI support;
- optional official ComfyUI provisioning;
- constrained owner-configured checkpoint repair;
- shared external model libraries without copying multi-GB model folders;
- checkpoint/LoRA/VAE/ControlNet/UNET/text-encoder/CLIP-vision/upscaler inventory;
- standard txt2img workflow;
- custom ComfyUI API workflow templates and live preflight;
- real ComfyUI prompt IDs and completion history;
- atomic output collection;
- bounded-concurrency batches;
- lock-protected shared task history;
- MCP v2 over stdio and private Streamable HTTP;
- native MCP image content for generated-image inspection;
- Claude Desktop configuration;
- private HTTP MCP Windows-login autostart;
- OpenAI Secure MCP Tunnel tooling for ChatGPT-to-workstation access;
- optional hardened REST/WebSocket gateway;
- authoritative cross-platform + Windows verification.

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

For a current checkout the pull is optional:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater fast-forwards safely, installs required dependencies, runs the authoritative verifier, configures supported agent integrations, repairs/provisions native ComfyUI when allowed, validates the real workflow/model contract and conditionally configures the ChatGPT tunnel when an OpenAI tunnel identity is available.

Useful switches:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipDependencies
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIProvision
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

## Verification

Fast structural/source verification:

```powershell
python evavo.py verify
```

Full gate:

```powershell
python evavo.py verify --full
```

Strict Windows gate including PowerShell AST parsing:

```powershell
python evavo.py verify --full --require-powershell
```

`verify-evavo.py` automatically discovers maintained root, `tests/`, and package test suites so new safety tests cannot silently fall outside the canonical setup path.

## CLI image generation

```powershell
python evavo.py generate `
  --prompts "PS1 horror corridor" `
  --project ps1 `
  --wait
```

Multiple prompts:

```powershell
python evavo.py generate `
  --prompts "corridor one" "corridor two" "corridor three" `
  --project ps1 `
  --wait
```

## Claude

Claude Desktop uses local **stdio MCP**:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after the configuration changes.

## ChatGPT

Cloud ChatGPT does not directly connect to workstation `127.0.0.1`.

EVAVO keeps its MCP server private on:

```text
http://127.0.0.1:8765/mcp
```

and uses the **OpenAI Secure MCP Tunnel** as the outbound bridge.

After the OpenAI tunnel has been created/associated:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_0123456789abcdef0123456789abcdef"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

Tunnel-client release and installed-executable integrity are SHA-256 verified. Optional persistent key storage uses current-user Windows DPAPI; the plaintext key is not stored in Git, `.evavo`, Claude configuration or Windows Startup.

See `CHATGPT-TUNNEL.md`.

## MCP tools

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

`generate_image` and `generate_batch` default to auto-starting the real backend and waiting for outputs.

Invalid file/wait policy is rejected **before backend startup and before queueing**. A request that fails this preflight does not create a fake generation task.

## MCP filesystem policy

MCP tools do not have arbitrary local filesystem authority.

Default output root:

```text
<repo>\.evavo\outputs\
```

Override the default root:

```powershell
$env:EVAVO_GENERATION_OUTPUT_DIR = "D:\EVAVO\generated"
```

Additional owner-approved output roots:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\ProjectA;E:\ApprovedRenders"
```

A tool-supplied `output_dir` outside those roots is rejected.

`read_output_image` accepts only authorized ordinary PNG/JPEG/GIF/WebP files. It rejects symlinked/redirected paths, empty/oversized files and extension-only fake images whose file signature does not match the claimed image type.

## Custom workflows

Preferred owner-selected default:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

The configured default is ordinary-file checked before use.

Tool-supplied workflow paths are **disabled by default**. To let an agent select among a reviewed workflow library:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

A supplied workflow must remain inside that owner-selected root and may not be a symlink or traverse a redirected parent path.

Supported placeholders include current uppercase and legacy lowercase forms:

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

`workflow_preflight` validates the same workflow against live ComfyUI without queueing a prompt or writing task history.

Claude and private-HTTP login installers preserve approved non-secret MCP path-policy variables. Signed checkpoint URLs are deliberately not persisted.

## Native ComfyUI

Default endpoint:

```text
http://127.0.0.1:8188
```

EVAVO uses:

```text
GET  /system_stats
GET  /object_info[/<node>]
POST /prompt
GET  /history/<prompt_id>
GET  /view
```

`COMFYUI_ENDPOINT` is canonical. `EVAVO_COMFYUI_ENDPOINT` remains a compatibility fallback.

An already-running user-managed native ComfyUI is reused and is never killed by EVAVO.

## Provisioning

```powershell
python provision-comfyui.py
```

EVAVO reuses existing reviewed source/portable installs before creating another checkout. Source installs use an isolated `.venv`; Windows-portable embedded Python is not modified. The provisioner does not silently choose or license a model.

Agent profiles can enable:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

Checkpoint repair still requires an owner-configured source such as `EVAVO_CHECKPOINT_FILE` or `EVAVO_CHECKPOINT_URL`. MCP tools cannot supply arbitrary model/repository URLs.

## Shared model libraries

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Alias:

```text
EVAVO_COMFYUI_MODEL_ROOTS
```

EVAVO generates `.evavo\extra-model-paths.yaml` and passes it to managed ComfyUI with `--extra-model-paths-config`; it does not overwrite ComfyUI's own configuration.

## Task history

CLI and MCP share lock-protected atomic task history. Records can include task ID, prompt/project, status, backend mode, checkpoint, workflow, output directory, all output URIs, errors and timestamps.

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

## Optional HTTP gateway

Default:

```text
http://127.0.0.1:8000
```

Owned image route:

```text
POST /generate/image
```

Optional delegated routes:

```text
POST /generate/video
POST /generate/audio
POST /generate/3d
```

Use:

```text
GET /services
```

to inspect auxiliary readiness. `202` means accepted, not completed. Missing/inadmissible providers fail the task with a structured `PROVIDER_*` error rather than fake completion.

Gateway protections include loopback-only binding, CORS off by default, pre-parse request-size limits including chunked requests, owner-root-confined optional workflow paths, ordinary-file result checks, fail-closed corrupt state and a single live gateway owner per task-state file.

## Status and recovery

Read-only aggregate status:

```powershell
.\AGENT-STATUS.ps1
.\AGENT-STATUS.ps1 -Json
```

Strict real-image readiness/repair:

```powershell
python agent-doctor.py --repair --provision
```

See `AGENT-RECOVERY.md` for recovery rules.

## Current source of truth

```text
README.md
CLAUDE.md
AGENT-INTEGRATION.md
AGENT-RECOVERY.md
OPERATIONS-GUIDE.md
QUICK-REFERENCE.md
DEPLOYMENT-CHECKLIST.md
GATEWAY-INTEGRATION-GUIDE.md
GATEWAY-AUX-PROVIDERS.md
PROVIDER-INTEGRATION-GUIDE.md
CHATGPT-TUNNEL.md
EVAVO-CAPABILITIES.json
.evavo/capabilities.json
```

Files explicitly labeled historical/superseded are provenance only and must not be used as current setup instructions.
