# EVAVO Local Image Generator

A Windows-first **native ComfyUI** image-generation control plane shared by CLI automation, Claude Desktop and ChatGPT. The EVAVO deterministic mock is test infrastructure only and cannot satisfy production rendering readiness.

## Production contract

This repository owns image generation:

```text
agent / CLI
  -> EVAVO lifecycle + policy
  -> native ComfyUI
  -> /prompt
  -> jobs/history/queue status
  -> /view
  -> validated atomic output
  -> shared task history
```

The optional loopback HTTP gateway may **delegate** video/audio/3D work to separately governed sibling EVAVO Studio providers. Those routes are not MCP/package-owned capabilities of this repository.

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

For a current checkout, just run:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater safely fast-forwards `main`, installs dependencies, runs the authoritative verifier, prepares/provisions native ComfyUI when allowed, and runs strict agent-doctor readiness. If strict doctor fails, it may make **one** evidence-gated core dependency repair attempt through the constrained shared repair bridge, unless `-SkipComfyUIDependencyRepair` is supplied. It then re-proves strict readiness, bootstraps native ComfyUI, installs/reloads Claude/private HTTP MCP, runs final doctor, and finally executes one **real native generation smoke proof**. Setup does not report success unless the active workflow actually renders and EVAVO downloads a signature-validated image. ChatGPT Secure MCP Tunnel configuration is then completed when its external tunnel identity/key are available.

The updater never enables `force_sync` dependency repair. That override requires explicit workstation-owner authorization through:

```powershell
$env:EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR = "1"
```

## Verification

```powershell
python evavo.py verify
python evavo.py verify --full
python evavo.py verify --full --require-powershell
```

`verify-evavo.py` auto-discovers maintained root, `tests/`, and package suites. Python syntax is compiled in memory and PowerShell setup scripts are AST-parsed on Windows. Simulator tests prove repository contracts but do **not** substitute for the real post-bootstrap render required by the canonical workstation updater.

Direct real-render proof:

```powershell
python real-generation-smoke.py --json
```

## CLI image generation

```powershell
python evavo.py generate --prompts "PS1 horror corridor" --project ps1 --wait
python evavo.py generate --prompts "corridor one" "corridor two" --project ps1 --wait
```

## Claude

Claude Desktop uses local **stdio MCP**:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after configuration changes.

## ChatGPT

Cloud ChatGPT does not directly reach workstation `127.0.0.1`. EVAVO keeps the local MCP server private and uses the **OpenAI Secure MCP Tunnel** as the outbound bridge.

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_0123456789abcdef0123456789abcdef"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

Tunnel-client release and executable integrity are SHA-256 verified. Optional persistent runtime-key storage uses current-user Windows DPAPI; plaintext keys are not stored in Git, `.evavo`, Claude config or Windows Startup. See `CHATGPT-TUNNEL.md`.

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

`generate_image` / `generate_batch` auto-start native ComfyUI and wait by default. Invalid file/wait policy is rejected **before backend startup and before queueing**, so a rejected preflight does not create a fake task.

`diagnose_backend` runs a bounded startup diagnostic. `last_startup_failure` returns the last structured startup failure without changing process state.

When a structured startup failure is `missing_dependency`, `repair_backend_dependencies` can synchronize the **exact diagnosed ComfyUI workdir's own requirements** with its recorded Python runtime; if exact runtime evidence is absent it falls back to the canonical discovered runtime. The MCP tool does not accept arbitrary package names, Python paths, ComfyUI paths or URLs, does not use a shell, and does not treat custom-node dependency failures as permission to mutate core ComfyUI. Normal recovery is:

```text
last_startup_failure
-> diagnose_backend
-> repair_backend_dependencies   # only for proven core missing_dependency
-> diagnose_backend
-> ensure_backend
-> real generation proof
```

`force_sync=true` is separately owner-gated by `EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR=1` and is never enabled by the canonical updater.

`generation_status` prefers current ComfyUI jobs and falls back to legacy history/queue, normalizing:

```text
queued
running
completed
failed
cancelled
unknown
```

`cancel_generation` cancels **one job**. Current ComfyUI uses its per-job cancel endpoint. Older servers may delete one proven-pending prompt, but EVAVO refuses broad `/interrupt` for a running legacy job because that could affect unrelated work.

## MCP filesystem policy

MCP is not arbitrary local filesystem authority.

Default output root:

```text
<repo>\.evavo\outputs\
```

Owner-approved additional roots:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\ProjectA;E:\ApprovedRenders"
```

A supplied `output_dir` outside approved roots is rejected.

Preferred owner-selected custom workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Tool-supplied workflow paths are disabled by default. To expose only a reviewed library:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

Workflow/output image paths must be ordinary files/directories under owner-authorized roots. Symlinks and redirected parent paths are rejected. `read_output_image` additionally validates PNG/JPEG/GIF/WebP signatures instead of trusting extensions.

Claude and private-HTTP login installers persist approved **non-secret** MCP path policy. Signed checkpoint URLs are deliberately not persisted.

## Native ComfyUI

Default:

```text
http://127.0.0.1:8188
```

Canonical environment variable:

```text
COMFYUI_ENDPOINT
```

Legacy alias: `EVAVO_COMFYUI_ENDPOINT`.

EVAVO uses current and compatibility routes including:

```text
GET  /system_stats
GET  /object_info[/<node>]
POST /prompt
GET  /api/jobs/<job_id>
POST /api/jobs/<job_id>/cancel
GET  /history/<prompt_id>
GET  /queue
POST /queue          # exact pending delete fallback only
GET  /view
```

A user-managed native ComfyUI is reused and never killed by EVAVO. Managed shutdown requires identity proof.

## Provisioning and models

```powershell
python provision-comfyui.py
```

EVAVO reuses reviewed source/portable installs, uses an isolated source `.venv`, does not modify Windows-portable embedded Python, and never silently chooses/licenses a model.

Owner-configured checkpoint repair can use `EVAVO_CHECKPOINT_FILE` or `EVAVO_CHECKPOINT_URL`. MCP tools cannot supply arbitrary model/repository URLs.

Shared libraries can be reused without copying multi-GB model trees:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

EVAVO writes its own `.evavo\extra-model-paths.yaml`; it does not overwrite ComfyUI's config.

## Task history

CLI and MCP share lock-protected atomic history including backend/checkpoint/workflow/output/error/status metadata. Failed and cancelled prompt states are reconciled into the same history. The real setup smoke proof also records its real prompt ID and validated output in that shared history.

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

## Optional HTTP gateway

Default loopback URL:

```text
http://127.0.0.1:8000
```

Owned route: `POST /generate/image`.

Optional delegated routes: `POST /generate/video`, `POST /generate/audio`, `POST /generate/3d`.

Use `GET /services` for delegated readiness. `202` means accepted, not completed. Unavailable/inadmissible providers fail with structured `PROVIDER_*` errors instead of fake success.

Gateway protections include loopback-only binding, CORS off by default, pre-parse request limits, owner-confined optional workflows, ordinary-file result identity checks, fail-closed corrupt state and one live gateway owner per task-state file.

## Current sources of truth

`README.md`, `CLAUDE.md`, `AGENT-INTEGRATION.md`, `AGENT-RECOVERY.md`, `OPERATIONS-GUIDE.md`, `QUICK-REFERENCE.md`, `GATEWAY-INTEGRATION-GUIDE.md`, `GATEWAY-AUX-PROVIDERS.md`, `PROVIDER-INTEGRATION-GUIDE.md`, `CHATGPT-TUNNEL.md`, `EVAVO-CAPABILITIES.json`, `.evavo/capabilities.json`.

Files explicitly labeled historical/superseded are provenance only and must not be used as current setup instructions.
