# EVAVO HTTP Gateway Integration Guide

The EVAVO Gateway is an **optional loopback HTTP compatibility layer for the verified native image-generation runtime**. MCP remains the preferred agent integration for Claude and ChatGPT.

The gateway does not expose the deterministic EVAVO mock as a production renderer and does not pretend unsupported modalities are queued.

## Network contract

Default addresses:

```text
Gateway:  http://127.0.0.1:8000
ComfyUI:  http://127.0.0.1:8188
```

`EVAVO_GATEWAY_HOST` is restricted to `127.0.0.1`, `localhost`, or `::1`. `0.0.0.0`/public binds are rejected.

The gateway should remain private. Cloud ChatGPT reaches EVAVO through the OpenAI Secure MCP Tunnel described in `CHATGPT-TUNNEL.md`, not by exposing port 8000.

## Current routes

| Method | Path | Contract |
|---|---|---|
| `GET` | `/health` | Gateway + **native ComfyUI** readiness |
| `GET` | `/capabilities` | Truthful supported/unsupported capability report |
| `POST` | `/generate/image` | Queue real native-ComfyUI image generation |
| `POST` | `/generate/video` | Compatibility route; returns HTTP `501` |
| `POST` | `/generate/audio` | Compatibility route; returns HTTP `501` |
| `POST` | `/generate/3d` | Compatibility route; returns HTTP `501` |
| `GET` | `/tasks` | List gateway tasks |
| `GET` | `/tasks/{task_id}/status` | Read one task |
| `GET` | `/results/{task_id}` | Download primary completed image |
| `WS` | `/ws/progress/{task_id}` | Task progress/status changes |

A fully ready health response is:

```json
{"status":"healthy","gateway":"ok","comfyui":"ok"}
```

When the gateway process is alive but native ComfyUI is unavailable, `/health` returns a degraded payload rather than treating the test mock as ready.

## Start / monitor / stop

Preferred convenience launcher:

```powershell
.\START-GATEWAY.ps1
```

Continuous compatibility monitoring:

```powershell
.\START-GATEWAY.ps1 -Monitor -Interval 5
```

Direct manager commands:

```powershell
python EVAVO-SERVICE-MANAGER.py start
python EVAVO-SERVICE-MANAGER.py health
python EVAVO-SERVICE-MANAGER.py monitor --interval 5
python EVAVO-SERVICE-MANAGER.py stop
```

The service manager shares the same native lifecycle used by CLI/MCP:

- reuse healthy user-managed native ComfyUI;
- discover/start an installed source or portable runtime;
- never accept the deterministic mock as production gateway health;
- never kill an unknown process occupying a port;
- stop only identity-verified EVAVO-managed gateway/native processes.

For fresh-machine provisioning use the canonical workstation updater or agent doctor first:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
# or
python agent-doctor.py --repair --provision
```

## Image generation

Queue:

```powershell
curl.exe -X POST http://127.0.0.1:8000/generate/image `
  -H "Content-Type: application/json" `
  -d '{"prompt":"a beautiful sunset over mountains","project_name":"gateway_demo"}'
```

Response:

```json
{"task_id":"img_<unique-id>","status":"queued","progress":0}
```

Optional fields are additive and include:

```text
project_name
negative_prompt
width
height
steps
cfg_scale
seed
checkpoint
workflow_path
wait_timeout
```

The worker uses the same `ComfyUIBackend` as CLI/MCP:

```text
ensure native backend
→ POST /prompt
→ GET /history/<prompt_id>
→ GET /view
→ atomic local download
→ persisted gateway/shared task history
```

Status:

```powershell
curl.exe http://127.0.0.1:8000/tasks/<task_id>/status
```

Result:

```powershell
curl.exe http://127.0.0.1:8000/results/<task_id> --output result.png
```

`/results/{task_id}` returns:

- HTTP `200` + image when completed;
- HTTP `202` while queued/running;
- HTTP `409` for a failed task;
- HTTP `404` for an unknown task;
- HTTP `410` if a recorded output is missing or fails the gateway result-path authorization boundary.

## Unsupported compatibility routes

Historical clients may still know these endpoints:

```text
/generate/video
/generate/audio
/generate/3d
```

They intentionally return HTTP `501`. They do **not** create fake tasks or report fake completion.

Use the dedicated EVAVO repositories/tools for non-image media.

## Capabilities

```powershell
curl.exe http://127.0.0.1:8000/capabilities
```

The response marks `image.ready` from native ComfyUI health and reports video/audio/3D as unavailable with an explicit reason.

## Real-time progress

```text
ws://127.0.0.1:8000/ws/progress/<task_id>
```

The socket emits the public task record when it changes and closes on terminal status.

## Persistence

Gateway-local state defaults to:

```text
.evavo/gateway/tasks.json
.evavo/gateway/results/<task_id>/
.evavo/gateway/logs/gateway.log
.evavo/gateway/service-manager.json
```

The gateway also mirrors status/output metadata into the shared `TaskTracker` on a best-effort basis. Interrupted queued/running gateway tasks are marked failed with `GATEWAY_RESTARTED` after a gateway restart rather than remaining falsely active.

## CORS

CORS is **off by default**. To opt in for specific local origins, set a comma-separated allowlist:

```powershell
$env:EVAVO_GATEWAY_CORS_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"
```

The gateway does not enable wildcard public CORS as part of its default contract.

## Validation

The isolated gateway integration suite is part of the authoritative verifier:

```powershell
python test-gateway.py
python evavo.py verify --full --require-powershell
```

It verifies:

- native-only health;
- truthful capabilities;
- `501` for unsupported modalities;
- image queue/completion/download through the native simulator;
- service-manager health agreement;
- rejection of public gateway binds.

For an already-running real gateway, the additional live smoke helper remains:

```powershell
python gateway-smoke-test.py
```

## API documentation

When running:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
```

## Agent guidance

For Claude and ChatGPT, prefer MCP because it exposes lifecycle repair, model inventory, workflow preflight, shared task history and native image-content return. The HTTP gateway exists for compatibility with scripts/clients that specifically need REST/WebSocket behavior.

See `AGENT-INTEGRATION.md` and `CHATGPT-TUNNEL.md` for the current agent architecture.
