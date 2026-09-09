# EVAVO Local Image Generator — Quick Reference

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

For a stale clean checkout first run `git pull --ff-only origin main`.

The updater safely fast-forwards `main`, installs dependencies, runs all discovered verifier suites, configures Claude/private MCP, provisions or repairs native ComfyUI when allowed, validates the real generation contract and conditionally configures the ChatGPT Secure MCP Tunnel.

## Verification / readiness

```powershell
python evavo.py verify
python evavo.py verify --full
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
.\AGENT-STATUS.ps1
```

The deterministic mock cannot satisfy strict production readiness.

## Claude

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses local **stdio MCP**. Restart Claude Desktop after configuration changes.

## ChatGPT

Private local MCP target:

```text
http://127.0.0.1:8765/mcp
```

Cloud ChatGPT reaches it through the **OpenAI Secure MCP Tunnel**, not by connecting directly to localhost.

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

## MCP tools

```text
provision_backend
ensure_backend
diagnose_backend
last_startup_failure
repair_backend_dependencies
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

### Startup diagnosis / dependency repair

Normal recovery order:

```text
last_startup_failure
-> diagnose_backend(seconds=60, cpu=true)
-> repair_backend_dependencies()   # only for structured core missing_dependency
-> diagnose_backend(seconds=60, cpu=true)
-> ensure_backend
-> real generation proof
```

`repair_backend_dependencies` uses only the selected ComfyUI checkout's own requirements + selected interpreter. MCP does not accept arbitrary package/module/Python/ComfyUI path arguments for repair, does not use a shell, and refuses to treat a `custom_node_dependency` failure as permission to sync core requirements.

### Generation status

`generation_status` prefers the current ComfyUI jobs API and falls back to legacy history/queue. States are:

```text
queued
running
completed
failed
cancelled
unknown
```

### Targeted cancellation

`cancel_generation` targets exactly one prompt/job.

- current ComfyUI: per-job cancel endpoint;
- older ComfyUI + pending prompt: exact pending queue delete;
- older ComfyUI + running prompt: EVAVO **refuses broad `/interrupt`** and reports targeted cancellation unsupported.

This avoids cancelling unrelated renderer work.

## MCP output/workflow policy

Default output root:

```text
<repo>\.evavo\outputs\
```

Owner-approved extras:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\ProjectA;E:\ApprovedRenders"
```

Preferred custom workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Allow agent selection only from a reviewed library:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

Arbitrary output directories/workflow files are denied. Symlinked or redirected paths are rejected. Generated images are signature-validated before promotion and again before MCP image delivery.

Invalid file/wait policy is rejected **before ComfyUI startup, queueing or task creation**.

## Real CLI image generation

```powershell
python evavo.py generate --prompts "PS1 horror corridor" --project ps1 --wait
python evavo.py generate --prompts "corridor one" "corridor two" --project ps1 --wait
```

## Models / provisioning

```powershell
python provision-comfyui.py
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Owner-configured checkpoint repair:

```powershell
$env:EVAVO_CHECKPOINT_FILE = "D:\AI\Models\model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<optional sha256>"
```

or explicit HTTPS `EVAVO_CHECKPOINT_URL`. Agent tools cannot invent arbitrary model URLs.

## Shared task history

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

CLI/MCP share atomic lock-protected task history including failed and cancelled reconciliation.

## Optional HTTP gateway

```text
http://127.0.0.1:8000
```

Owned image route: `/generate/image`.

Optional governed delegation: `/generate/video`, `/generate/audio`, `/generate/3d`.

Use `/services` to check provider readiness. Missing providers fail closed; `202` means accepted, not completed.

## Source of truth

See `README.md`, `CLAUDE.md`, `AGENT-INTEGRATION.md`, `OPERATIONS-GUIDE.md`, `CHATGPT-TUNNEL.md`, `GATEWAY-INTEGRATION-GUIDE.md`, `EVAVO-CAPABILITIES.json`.
