# EVAVO Provider Integration Guide

## Ownership model

`evavo-local-image-generator` owns and verifies **native image generation**. Native ComfyUI is its production renderer.

The optional HTTP gateway may additionally **delegate** video, audio and 3D requests to separately governed sibling EVAVO Studio providers. Delegation does not make those modalities owned capabilities of this repository, and they are not added to its MCP tool surface.

```text
owned here:       image -> native ComfyUI
delegated only:   video -> EVAVO Video Studio / reviewed provider
                  audio -> reviewed Audio Studio provider
                  3d    -> token-gated EVAVO 3D Studio worker
```

## Fail-closed provider rule

A provider route may accept an asynchronous request with HTTP `202`, but that means only **accepted for processing**. Completion requires:

- a provider that is actually ready;
- a bounded, reviewed execution interface;
- a valid success receipt;
- a real artifact;
- path confinement to the admitted task workspace;
- hash verification when supplied by the provider;
- timeout/error handling.

If those conditions are not satisfied, the gateway task moves to `failed` with a structured `PROVIDER_*` error. It must never invent task success or an output file.

## Readiness

Core image readiness:

```text
GET http://127.0.0.1:8000/health
```

Per-provider readiness:

```text
GET http://127.0.0.1:8000/services
GET http://127.0.0.1:8000/capabilities
```

Auxiliary availability is deliberately separate from core image health.

## Image provider

Default native ComfyUI endpoint:

```text
http://127.0.0.1:8188
```

Preferred environment variable:

```text
COMFYUI_ENDPOINT
```

`EVAVO_COMFYUI_ENDPOINT` remains a compatibility fallback.

The owned image path uses:

```text
GET  /system_stats
GET  /object_info[/<node>]
POST /prompt
GET  /history/{prompt_id}
GET  /view
```

## Delegated CLI providers

Where a Studio exposes a reviewed CLI provider, EVAVO accepts an **argument-array contract**, not an arbitrary shell command. The provider runner uses `asyncio.create_subprocess_exec`; `shell=True` is not used.

The provider must emit a machine-readable success receipt and identify an artifact inside the provider task directory. Environment-specific details are documented in `GATEWAY-AUX-PROVIDERS.md`.

## 3D provider

The 3D route uses the existing governed 3D Studio worker contract: loopback endpoint, explicit execution enablement, workspace confinement and bearer token. EVAVO validates health/capabilities, compiles the job through the worker, submits it, polls status, accepts only the expected completion receipt, confines the artifact path and verifies its digest when present.

The gateway does not promote a 3D candidate beyond the authority granted by the 3D Studio worker.

## Security

- gateway remains loopback-only;
- CORS is disabled by default and wildcard/non-loopback origins are rejected;
- no generic shell execution;
- no fake success from exit code `0` alone;
- provider stdout/stderr retention is bounded;
- timeouts terminate provider children safely;
- result path traversal/symlink escapes are rejected;
- provider receipts remain internal task evidence;
- unavailable providers fail closed.

## Verification

```powershell
python evavo.py verify --full --require-powershell
```

The authoritative verifier runs both isolated gateway tests and the provider suites under `tests/`, including CLI provider success, output escape rejection, governed 3D worker flow and service-manager provider safety.

See:

- `GATEWAY-INTEGRATION-GUIDE.md` for the HTTP contract;
- `GATEWAY-AUX-PROVIDERS.md` for provider-specific setup;
- `EVAVO-CAPABILITIES.json` for the machine-readable ownership boundary.
