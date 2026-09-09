# EVAVO Agent Integration

This repository owns one production generation capability: **local image generation through native ComfyUI**. Claude, ChatGPT, local MCP clients, direct Python automation and `evavo.py` share the same lifecycle, model, workflow, task-history and output-integrity contract.

The deterministic EVAVO mock is test infrastructure only.

The optional loopback HTTP gateway may separately **delegate** video/audio/3D jobs to governed sibling EVAVO Studio providers. Those delegated routes are not MCP/package-owned capabilities of this image-generator repository.

## Canonical Windows convergence

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Authoritative validation:

```powershell
python evavo.py verify --full --require-powershell
```

The verifier discovers maintained root, `tests/`, and package suites automatically.

## Claude

Claude Desktop uses local **stdio MCP**:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after configuration changes.

## ChatGPT

Cloud ChatGPT does not directly reach workstation localhost. EVAVO keeps MCP private and uses the **OpenAI Secure MCP Tunnel** as the outbound bridge.

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

See `CHATGPT-TUNNEL.md`.

## MCP tool surface

```text
provision_backend
ensure_backend
diagnose_backend
last_startup_failure
health_check
discover_backends
list_checkpoints
model_inventory
workflow_preflight
generate_image
generate_batch
generation_status
cancel_generation
collect_generation
read_output_image
task_history
task_statistics
stop_managed_backend
```

There are intentionally no `generate_video`, `generate_audio` or `generate_3d` MCP tools here.

## Normal one-call generation

`generate_image` and `generate_batch` default to `auto_start=true` and `wait=true`. EVAVO can:

1. validate request/file policy before backend work;
2. reject the deterministic mock as a renderer;
3. reuse or discover native ComfyUI;
4. optionally provision the fixed official runtime when owner policy permits;
5. attach owner-configured shared model roots;
6. inventory live model loaders;
7. preflight a custom API workflow;
8. queue `/prompt` and retain the real prompt ID;
9. normalize jobs/history/queue state;
10. wait and collect `/view` image output;
11. validate image signatures before final promotion;
12. persist completion/failure/cancellation evidence to shared task history;
13. return local paths and optional MCP image content.

Invalid file/wait policy is rejected **before ComfyUI is started, before queueing and before task creation**.

## Diagnostics

Use:

```text
diagnose_backend
last_startup_failure
```

`diagnose_backend` performs a bounded startup diagnostic against only the process tree created by that probe. `last_startup_failure` returns the last structured startup failure without changing process state.

This is preferred over broad process cleanup.

## Generation status

`generation_status` prefers the current ComfyUI jobs API and falls back to legacy history/queue. It returns one of:

```text
queued
running
completed
failed
cancelled
unknown
```

A failed ComfyUI execution is persisted as failed rather than left looking queued. A prompt absent from both history and queue is `unknown`, not invented as queued.

## Targeted cancellation

`cancel_generation` targets **one job**.

- current ComfyUI: idempotent per-job cancel endpoint;
- older ComfyUI + proven pending prompt: exact pending queue delete;
- older ComfyUI + running prompt: EVAVO returns `COMFYUI_TARGETED_CANCEL_UNSUPPORTED` rather than using broad `/interrupt`.

The last rule is deliberate because broad legacy interrupt could affect work other than the requested task.

## MCP filesystem authority

MCP generation is not arbitrary filesystem read/write authority.

Default output root:

```text
<repo>\.evavo\outputs\
```

Owner-approved extra roots:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\Generated;E:\ApprovedProjectRenders"
```

A tool-supplied `output_dir` outside approved roots is rejected.

Preferred production workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Tool-supplied workflow paths are disabled by default. To expose a reviewed workflow library:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

Workflow/output image files must be ordinary files. Symlinks and redirected parent paths are rejected. Generated-image content must match its PNG/JPEG/GIF/WebP signature.

Claude and private HTTP login profiles preserve only approved **non-secret** policy. `EVAVO_CHECKPOINT_URL` is not copied because signed URLs may contain credentials.

## Models and workflow preflight

`model_inventory` reports checkpoints, LoRAs, VAEs, ControlNet, diffusion/UNET models, text encoders, CLIP vision and upscalers independently.

`workflow_preflight` validates node classes, required inputs and literal loader choices without queueing a prompt or writing task history.

Runtime/model owner configuration can include:

```text
COMFYUI_ENDPOINT
EVAVO_COMFYUI_HOME
EVAVO_COMFYUI_PYTHON
EVAVO_COMFYUI_SEARCH_PATHS
EVAVO_COMFYUI_CHECKPOINT
EVAVO_COMFYUI_WORKFLOW
EVAVO_SHARED_MODEL_ROOTS
EVAVO_CHECKPOINT_FILE
EVAVO_CHECKPOINT_URL
EVAVO_CHECKPOINT_SHA256
EVAVO_AUTO_PROVISION_COMFYUI
EVAVO_AUTO_PROVISION_CHECKPOINT
EVAVO_GENERATION_OUTPUT_DIR
EVAVO_TASK_HISTORY
```

Do not invent a model source when the workstation owner has not configured one.

## Shared task history

CLI and MCP share lock-protected atomic task history including queued/running/completed/failed/cancelled states plus backend/checkpoint/workflow/output/error metadata.

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

## Optional gateway

Private loopback gateway:

```text
http://127.0.0.1:8000
```

Owned: `POST /generate/image`.

Optional delegated: `POST /generate/video`, `POST /generate/audio`, `POST /generate/3d`.

Use `GET /services` to inspect provider readiness. `202` means accepted, not completed. Missing/inadmissible providers fail closed with structured `PROVIDER_*` errors.

Gateway protections include CORS off by default, pre-parse body limits, owner-confined workflow paths, ordinary-file result identity, corrupt-state fail-closed behavior, interprocess locks and one live gateway owner per task-state file.

See `GATEWAY-INTEGRATION-GUIDE.md` and `GATEWAY-AUX-PROVIDERS.md`.

## Recovery

```powershell
.\AGENT-STATUS.ps1
python agent-doctor.py --repair --provision
```

See `AGENT-RECOVERY.md`. Recovery must never broadly kill `python.exe`, expose raw local ports publicly, overwrite `.git`, force-push or regenerate current source from historical templates.
