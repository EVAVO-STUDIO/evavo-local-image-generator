# EVAVO HTTP Gateway Integration Guide

The EVAVO Gateway is an **optional loopback HTTP compatibility layer**. This repository owns and verifies the native ComfyUI **image** pipeline. The gateway may also delegate video, audio and 3D requests to separately governed sibling EVAVO Studio providers when those providers are explicitly ready.

MCP remains the preferred agent integration for Claude and ChatGPT. Delegated gateway media is **not added to the MCP tool surface** of this image-generator repository.

## Ownership boundary

```text
Owned here
  image -> native ComfyUI

Optional delegated gateway routes
  video -> reviewed EVAVO Video Studio/provider
  audio -> reviewed configured Audio Studio/provider
  3d    -> token-gated EVAVO 3D Studio worker
```

A delegated provider being absent never becomes fake success. The HTTP request is accepted as an asynchronous task, then the task fails closed with a structured provider error when no admissible provider can execute it.

## Network contract

Default addresses:

```text
Gateway:  http://127.0.0.1:8000
ComfyUI:  http://127.0.0.1:8188
```

`EVAVO_GATEWAY_HOST` is restricted to `127.0.0.1`, `localhost`, or `::1`. Public binds are rejected.

CORS is **disabled by default**. If `EVAVO_GATEWAY_CORS_ORIGINS` is configured, every origin must be an explicit loopback HTTP/HTTPS origin with a valid port. Wildcard CORS is rejected.

Cloud ChatGPT reaches the workstation through the OpenAI Secure MCP Tunnel described in `CHATGPT-TUNNEL.md`; do not expose port 8000 publicly.

## Request and configuration safety

The gateway bounds generation requests before they become large Pydantic objects. `EVAVO_GATEWAY_MAX_REQUEST_BYTES` defaults to 1 MiB and is clamped to a maximum of 16 MiB. The ASGI ingress middleware checks declared `Content-Length` immediately and also counts streaming/chunked request bytes, so omitting a length header does not bypass the limit.

Additional request boundaries:

```text
EVAVO_GATEWAY_MAX_PROMPT_CHARS   default 100000, hard cap 1000000
EVAVO_GATEWAY_MAX_PROJECT_CHARS  default 128, hard cap 1024
EVAVO_GATEWAY_IMAGE_TIMEOUT      default 600 seconds, bounded 1..86400
```

Malformed numeric configuration fails at startup with a stable `GATEWAY_CONFIG_INVALID:<variable>:...` error instead of an unclassified Python conversion failure. Non-finite numeric values such as `nan` are rejected.

### Request-supplied workflows

Per-request `workflow_path` is **denied by default** on `/generate/image`. Prefer owner-configured `EVAVO_COMFYUI_WORKFLOW` for the normal production workflow.

If a workstation owner deliberately needs request-supplied workflows, both an explicit allow switch **and** an existing owner-selected root are required:

```powershell
$env:EVAVO_GATEWAY_WORKFLOW_ROOT = "D:\EVAVO\workflows"
$env:EVAVO_GATEWAY_ALLOW_REQUEST_WORKFLOW_PATHS = "1"
```

The gateway resolves the requested file strictly and requires the resulting path to remain inside `EVAVO_GATEWAY_WORKFLOW_ROOT`. Missing files and path escapes fail before a task is queued. Symlink/path resolution therefore cannot be used to escape the admitted root.

Do not enable request-supplied workflows for an untrusted HTTP client. The gateway is private loopback infrastructure, not a general arbitrary-file workflow service.

## Routes

| Method | Path | Contract |
|---|---|---|
| `GET` | `/health` | Gateway + native ComfyUI core readiness |
| `GET` | `/services` | Native image + auxiliary provider readiness |
| `GET` | `/capabilities` | Per-modality readiness projection |
| `POST` | `/generate/image` | Queue owned native-ComfyUI image generation |
| `POST` | `/generate/video` | Queue delegated video task |
| `POST` | `/generate/audio` | Queue delegated audio task |
| `POST` | `/generate/3d` | Queue delegated 3D task |
| `GET` | `/tasks` | List gateway tasks |
| `GET` | `/tasks/{task_id}/status` | Read one task |
| `GET` | `/results/{task_id}` | Download the primary completed artifact |
| `WS` | `/ws/progress/{task_id}` | Task progress/status changes |

All generation POST routes use HTTP `202` because work is asynchronous. `202` means **accepted**, not completed.

## Core health

A fully ready core response remains:

```json
{"status":"healthy","gateway":"ok","comfyui":"ok"}
```

`/health` deliberately reflects the owned image renderer, not optional auxiliary providers. Use `/services` when an agent needs to know whether video/audio/3D delegation is currently available.

The service manager's `health`/`status` command additionally reports its own ownership-state health. A running gateway can therefore have healthy core rendering while the manager reports overall `degraded` because safe lifecycle ownership metadata is corrupt.

## Start / monitor / stop

```powershell
.\START-GATEWAY.ps1
python EVAVO-SERVICE-MANAGER.py health
python EVAVO-SERVICE-MANAGER.py monitor --interval 5
python EVAVO-SERVICE-MANAGER.py stop
```

The service manager:

- requires/reuses real native ComfyUI for owned image generation;
- never treats the deterministic EVAVO mock as production rendering;
- never kills an unknown process occupying a port;
- stops only identity-verified EVAVO-managed processes;
- reports auxiliary provider readiness separately from core image health;
- fingerprints effective provider configuration without storing provider bearer-token plaintext;
- restarts only an identity-verified **managed** gateway when provider configuration changes;
- never kills an externally owned gateway merely to apply new provider settings;
- treats a missing `service-manager.json` as normal first-run state;
- treats malformed/unreadable/unsafe manager state as a lifecycle safety error rather than silently replacing it with `{}`.

If `service-manager.json` is corrupt, `health` reports degraded manager state while preserving the file for diagnosis. `start`, `stop`, and `monitor` fail closed before provider/backend/process mutation because EVAVO cannot safely prove what it owns. A symlinked manager-state file is also rejected.

For fresh-machine repair/provisioning:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
# or
python agent-doctor.py --repair --provision
```

## Image generation

```powershell
curl.exe -X POST http://127.0.0.1:8000/generate/image `
  -H "Content-Type: application/json" `
  -d '{"prompt":"a beautiful sunset over mountains","project_name":"gateway_demo"}'
```

The worker uses the same native `ComfyUIBackend` as CLI/MCP:

```text
ensure native backend
-> POST /prompt
-> GET /history/<prompt_id>
-> GET /view
-> atomic local download
-> persisted gateway/shared task history
```

## Auxiliary provider delegation

Before asking for delegated media, inspect:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services | ConvertTo-Json -Depth 8
```

The provider layer is intentionally narrower than arbitrary shell execution. Depending on modality it uses reviewed sibling workers or explicit JSON argument arrays, requires a valid provider success receipt and real artifact, constrains output paths to the admitted task workspace, applies bounded timeouts and verifies hashes when the provider supplies them.

Typical failure codes include:

```text
PROVIDER_UNAVAILABLE
PROVIDER_FAILED
PROVIDER_PROTOCOL_ERROR
PROVIDER_OUTPUT_INVALID
PROVIDER_TIMEOUT
```

A failed delegated task remains visible through `/tasks/{task_id}/status` and `/results/{task_id}` returns the failed task contract rather than inventing an output.

See `GATEWAY-AUX-PROVIDERS.md` for the provider-specific controls.

## Result contract

`/results/{task_id}` returns:

- HTTP `200` + artifact when completed;
- HTTP `202` while queued/running;
- HTTP `409` for a failed task;
- HTTP `404` for an unknown task;
- HTTP `410` if a recorded output is missing or violates the result-path authorization boundary.

## Persistence and live ownership

```text
.evavo/gateway/tasks.json
.evavo/gateway/tasks.json.lock
.evavo/gateway/tasks.json.instance.lock
.evavo/gateway/results/<task_id>/
.evavo/gateway/logs/gateway.log
.evavo/gateway/service-manager.json
```

Gateway task state is atomically written and guarded by the public `evavo_operations.interprocess_lock` primitive also used by EVAVO task history. The older `_interprocess_lock` name remains only as an in-repository compatibility alias. Task-ID allocation and insertion occur inside one mutation critical section, and all reads/mutations refresh persisted state under that lock.

A separate lifetime **instance lock** protects recovery semantics: exactly one live gateway may own a given `tasks.json` at a time. A second gateway can run on another port only when it uses a different task-state file. If it points at the same task state, startup fails with:

```text
GATEWAY_STATE_IN_USE:<task-state-path>
```

This is deliberate. Allowing two live processes to share a task store would make `GATEWAY_RESTARTED`/orphan recovery ambiguous even if individual writes were serialized. The first gateway remains authoritative and continues running; the second process does not mutate the shared task state.

Interrupted queued/running gateway tasks are marked failed with `GATEWAY_RESTARTED` after the owning gateway restarts instead of remaining falsely active.

Malformed/corrupt `tasks.json` is **not** treated as an empty task store. Gateway startup fails with `GATEWAY_TASK_STATE_CORRUPT` (or a read error) and leaves the original file untouched for diagnosis/recovery instead of silently overwriting task history.

Manager ownership metadata has the same fail-closed principle: malformed `service-manager.json` is reported with `SERVICE_MANAGER_STATE_CORRUPT` and is not silently reset before lifecycle operations.

## CORS

No cross-origin browser access is enabled by default. Optional local-only example:

```powershell
$env:EVAVO_GATEWAY_CORS_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"
```

`*`, non-loopback origins, and invalid ports are rejected.

## Validation

The authoritative verifier discovers root, `tests/`, and package suites:

```powershell
python evavo.py verify --full --require-powershell
```

Coverage includes native image flow, unavailable-provider fail-closed behavior, provider receipt/output confinement and digest evidence, provider secret/state handling, service-manager ownership-state corruption, loopback binding, structured startup configuration errors, CORS defaults, declared and chunked request-size limits, workflow-root confinement, bounded project names, restart-safe task IDs, mutation locking, **single live gateway ownership per task state**, and corrupt-state fail-closed startup.

For an already-running real gateway:

```powershell
python gateway-smoke-test.py
```

## Agent guidance

Claude/ChatGPT should use this repository's MCP tools for owned image generation, lifecycle repair, model inventory, workflow preflight, task history and image inspection. Use the gateway only when REST/WebSocket compatibility or governed delegation to sibling Studios is specifically needed.

See `AGENT-INTEGRATION.md`, `GATEWAY-AUX-PROVIDERS.md`, and `CHATGPT-TUNNEL.md`.
