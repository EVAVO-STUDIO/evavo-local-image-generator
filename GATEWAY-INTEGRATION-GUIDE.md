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

CORS is **disabled by default**. If `EVAVO_GATEWAY_CORS_ORIGINS` is configured, every origin must be an explicit loopback HTTP/HTTPS origin. Wildcard CORS is rejected.

Cloud ChatGPT reaches the workstation through the OpenAI Secure MCP Tunnel described in `CHATGPT-TUNNEL.md`; do not expose port 8000 publicly.

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
- reports auxiliary provider readiness separately from core image health.

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

The provider layer is intentionally narrower than arbitrary shell execution. Depending on modality it uses reviewed sibling workers or explicit JSON argument arrays, requires a valid provider success receipt and real artifact, constrains output paths to the admitted task workspace, applies timeouts and verifies hashes when the provider supplies them.

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

## Persistence

```text
.evavo/gateway/tasks.json
.evavo/gateway/results/<task_id>/
.evavo/gateway/logs/gateway.log
.evavo/gateway/service-manager.json
```

Interrupted queued/running gateway tasks are marked failed with `GATEWAY_RESTARTED` after restart instead of remaining falsely active.

## CORS

No cross-origin browser access is enabled by default. Optional local-only example:

```powershell
$env:EVAVO_GATEWAY_CORS_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"
```

`*` and non-loopback origins are rejected.

## Validation

The authoritative verifier discovers root, `tests/`, and package suites:

```powershell
python evavo.py verify --full --require-powershell
```

Coverage includes native image flow, unavailable-provider fail-closed behavior, provider receipt/output confinement, service-manager provider safety, loopback binding, and CORS defaults.

For an already-running real gateway:

```powershell
python gateway-smoke-test.py
```

## Agent guidance

Claude/ChatGPT should use this repository's MCP tools for owned image generation, lifecycle repair, model inventory, workflow preflight, task history and image inspection. Use the gateway only when REST/WebSocket compatibility or governed delegation to sibling Studios is specifically needed.

See `AGENT-INTEGRATION.md`, `GATEWAY-AUX-PROVIDERS.md`, and `CHATGPT-TUNNEL.md`.
