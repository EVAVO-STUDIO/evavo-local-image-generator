# Claude operating notes — EVAVO Local Image Generator

Read `AGENTS.md` first. This repository is the verified **native ComfyUI image-generation control plane**. Claude must use the same lifecycle, diagnostics, repair and evidence semantics as ChatGPT and other EVAVO agents. Do not revive historical BeeStation, Ollama/Kokoro, fake multimodal, source-regeneration, blanket-process-kill or destructive Git-repair paths.

## Preferred interface

Claude Desktop uses local **stdio MCP** through the policy-validated production entrypoint:

```text
python -m evavo_local_image_generator.mcp_entry --transport stdio
```

`evavo_local_image_generator.mcp_server` is the shared implementation/test module. Supported production profiles launch `mcp_entry`, which validates owner filesystem authority before importing/starting the long-lived server.

Install/update Claude's profile with:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

The installer validates MCP filesystem policy before creating, backing up or writing Claude configuration, even when the expensive integration suite is skipped. The normalized approved generation output root is what gets persisted.

Canonical workstation convergence:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Restart Claude Desktop after MCP configuration changes.

## Current MCP tools

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

Use `generate_image` / `generate_batch` for normal work. They auto-start native ComfyUI and wait for completed files by default.

For startup trouble use this exact shared recovery order:

```text
last_startup_failure
diagnose_backend(seconds=60, cpu=true)
repair_backend_dependencies()  # only when category == missing_dependency
diagnose_backend(seconds=60, cpu=true)
ensure_backend
real generation proof
```

`repair_backend_dependencies` is agent-safe: normal mutation requires structured core missing-dependency evidence, it uses the selected ComfyUI checkout's own requirements and Python runtime, it does not accept arbitrary package/Python/path authority, it never invokes a shell, and it returns a structured receipt. If the category is `custom_node_dependency`, do not sync core requirements; isolate with `disable_all_custom_nodes=true` and repair the reviewed custom node separately.

`force_sync=true` additionally requires workstation-owner authorization via `EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR=1`; normal automatic recovery never enables that override.

`generation_status` normalizes current ComfyUI jobs plus legacy history/queue state into:

```text
queued
running
completed
failed
cancelled
unknown
```

`cancel_generation` targets **one prompt/job**. Current ComfyUI uses the per-job cancel endpoint. On older servers EVAVO can delete an exact pending prompt, but it deliberately refuses broad `/interrupt` for a running legacy job because that could affect unrelated work.

Use `workflow_preflight` before long runs with exported API workflows. Use `model_inventory` to inspect checkpoints, LoRAs, VAEs, ControlNet, UNET/diffusion models, text encoders, CLIP vision and upscalers. Use `read_output_image` when Claude needs the actual generated image as MCP image content.

## File authority

MCP is not arbitrary filesystem access.

Default output root:

```text
<repo>\.evavo\outputs\
```

Additional output roots are workstation-owner configuration only:

```text
EVAVO_MCP_OUTPUT_ROOTS
```

Additional output roots must already exist, be ordinary non-symlink directories and be writable. The validated production entry rechecks this policy at every server start.

Tool-supplied custom workflows are disabled by default. Owner-approved selection requires:

```text
EVAVO_MCP_ALLOW_WORKFLOW_PATHS=1
EVAVO_MCP_WORKFLOW_ROOT=<reviewed workflow directory>
```

The preferred single production workflow is owner-side `EVAVO_COMFYUI_WORKFLOW`.

Generated-image reads and workflow paths require ordinary files; symlinks and redirected parent paths are rejected. PNG/JPEG/GIF/WebP content is signature-checked. Invalid file/wait policy is rejected before ComfyUI is started and before a task is created.

The Claude installer persists approved **non-secret** MCP roots/policy. It does not persist `EVAVO_CHECKPOINT_URL`, because signed URLs may contain credentials.

## Runtime behavior

EVAVO can discover/provision/start native ComfyUI, reject the deterministic mock as production rendering, reuse user-managed ComfyUI without killing it, inject EVAVO-owned shared model paths, repair proven core dependency drift from the checkout's own requirements, repair only owner-configured checkpoint sources, preflight workflows, submit `/prompt`, normalize job/history/queue state, download `/view` images atomically, validate image signatures and persist shared CLI/MCP history.

A user-managed ComfyUI is never killed. Managed shutdown requires process-identity proof.

Preferred endpoint variable:

```text
COMFYUI_ENDPOINT
```

Legacy alias:

```text
EVAVO_COMFYUI_ENDPOINT
```

## Scope boundary

This repository **owns production image generation only**.

The optional loopback HTTP gateway may delegate video, audio and 3D work to separately governed sibling EVAVO Studio providers when `/services` reports them ready. Those delegated routes are **not** MCP/package-owned capabilities of this repository, and unavailable providers fail closed instead of fabricating success.

Use the dedicated Studio repositories for direct video/audio/3D ownership.

## Verification and recovery

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py status
.\AGENT-STATUS.ps1
```

The canonical updater also runs a real native-ComfyUI smoke generation and refuses to report success unless a downloaded image passes EVAVO signature validation.

For ComfyUI startup trouble, prefer MCP `diagnose_backend`, `last_startup_failure` and `repair_backend_dependencies` over broad process cleanup or manual double-click instructions. If MCP lacks a needed local execution primitive, use EVAVO Local Compute's structured workstation bridge/operator and require terminal receipt evidence.

## Security rules

- keep ComfyUI, MCP HTTP and the optional gateway on loopback;
- cloud ChatGPT uses the OpenAI Secure MCP Tunnel, never a public raw localhost port;
- use `mcp_entry` for production MCP launch so filesystem policy is validated before server start;
- never use blanket `taskkill /IM python.exe` or destructive `.git` repair;
- never invent/download a model source when the owner has not configured one;
- do not persist signed checkpoint URLs or OpenAI tunnel runtime keys into repo/startup plaintext;
- use current-user DPAPI for optional persistent tunnel key storage;
- use per-job cancellation; never broad-interrupt a legacy running queue on behalf of one task;
- never claim a repair, process start or generation succeeded without the corresponding structured receipt/output evidence.

Current sources of truth: `AGENTS.md`, `README.md`, `AGENT-INTEGRATION.md`, `COMFYUI-STARTUP-DIAGNOSTICS.md`, `OPERATIONS-GUIDE.md`, `CHATGPT-TUNNEL.md`, `GATEWAY-INTEGRATION-GUIDE.md`, and `QUICK-REFERENCE.md`.
