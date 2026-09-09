# EVAVO Provider Integration Guide

## Current status

`evavo-local-image-generator` is the production control plane for **local image generation only**. Its optional HTTP gateway does not currently dispatch video, audio, 3D, particle, text, or dedicated PBR-texture work to other repositories.

That boundary is intentional. It prevents this repository from claiming a modality is queued or completed when another Studio has not actually executed it.

## Gateway contract

The compatibility gateway listens on loopback only:

```text
http://127.0.0.1:8000
```

Production behavior:

- `GET /health` requires a healthy native ComfyUI renderer;
- `GET /capabilities` reports image availability truthfully;
- `POST /generate/image` queues real native ComfyUI image work;
- `POST /generate/video` returns HTTP `501`;
- `POST /generate/audio` returns HTTP `501`;
- `POST /generate/3d` returns HTTP `501`;
- `/tasks`, `/tasks/{task_id}/status`, `/results/{task_id}` and WebSocket progress remain available for image tasks.

The deterministic EVAVO mock is test infrastructure and cannot make the production gateway healthy.

## Dedicated Studio ownership

Non-image modalities belong to their dedicated EVAVO repositories. This repository must not silently shell out to them, fabricate provider task IDs, or promote their candidate artifacts as successful image-generator results.

If EVAVO needs a future cross-Studio orchestration layer, implement it as an explicit orchestration contract with its own:

- capability discovery;
- provider identity/version checks;
- request/receipt schemas;
- authentication and authority boundaries;
- task ownership and cancellation semantics;
- artifact confinement and digest verification;
- timeout/retry behavior;
- end-to-end tests against the actual provider;
- truthful unavailable/not-implemented responses.

Do not add a provider adapter to this gateway merely to preserve an old endpoint name.

## Image provider

Native ComfyUI is the one production provider in this repository.

Default endpoint:

```text
http://127.0.0.1:8188
```

Preferred environment variable:

```text
COMFYUI_ENDPOINT
```

`EVAVO_COMFYUI_ENDPOINT` remains a legacy fallback alias.

The image path uses the shared `ComfyUIBackend` and native routes:

```text
GET  /system_stats
GET  /object_info
POST /prompt
GET  /history/{prompt_id}
GET  /view
```

Custom ComfyUI API workflows are live-preflighted before queueing when configured.

## Verification

Repository contract:

```powershell
python evavo.py verify --full --require-powershell
```

Gateway isolated integration test:

```powershell
python test-gateway.py
```

Live gateway smoke test after starting the real gateway/native renderer:

```powershell
python gateway-smoke-test.py
```

The tests verify that unsupported modalities fail explicitly rather than producing fake queued tasks.

## Historical note

Older revisions of this document described Video Studio/Wan, Audio Studio and 3D Studio provider adapters behind the unified gateway. That design is superseded. The current gateway source and `GATEWAY-INTEGRATION-GUIDE.md` are authoritative.
