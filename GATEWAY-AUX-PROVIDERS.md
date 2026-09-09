# EVAVO Gateway Auxiliary Providers

The Unified Gateway keeps native ComfyUI as its **owned, required image renderer** while optionally delegating other media to separately governed first-party sibling Studios or reviewed provider commands.

Core compatibility stays local and stable:

```text
Gateway:  http://127.0.0.1:8000
ComfyUI:  http://127.0.0.1:8188
health:   {"status":"healthy","gateway":"ok","comfyui":"ok"}
```

CORS is **disabled by default**. If browser access is needed, `EVAVO_GATEWAY_CORS_ORIGINS` accepts explicit loopback HTTP/HTTPS origins only. Wildcard and non-loopback origins are rejected.

Auxiliary provider availability does not control core image health. Inspect it through:

```text
GET /services
GET /capabilities
```

## Video Studio / Wan provider

Video can use either an explicitly configured reviewed CLI provider or the sibling EVAVO Video Studio Wan worker.

Explicit provider:

```text
EVAVO_VIDEO_PROVIDER_ARGV
EVAVO_VIDEO_PROVIDER_TIMEOUT
```

The argv value is a JSON string array, never a shell command.

Sibling Wan discovery checks:

```text
EVAVO_VIDEO_STUDIO_DIR
../evavo-video-studio
../video-studio
```

and requires the reviewed worker:

```text
tools/wan21_t2v_worker.py
```

The normal Wan path also requires:

```text
EVAVO_WAN21_MODEL_DIR
```

with `evavo-model-manifest.json` inside that model directory. Optionally pin the manifest itself with:

```text
EVAVO_WAN21_MODEL_MANIFEST_SHA256
```

Generation validates the manifest SHA policy, requires a successful worker JSON receipt, requires a non-trivial `video.mp4`, verifies the receipt's video SHA-256, and copies only the admitted task-local artifact into gateway results.

Optional Python override:

```text
EVAVO_VIDEO_PYTHON
```

## Audio Studio

When `evavo-audio-studio` is a sibling checkout and contains `worker_provider.py`, `START-GATEWAY.ps1` / `EVAVO-SERVICE-MANAGER.py` can automatically configure the existing JSON-argv provider boundary. An explicit `EVAVO_AUDIO_PROVIDER_ARGV` wins.

Normal sibling layout:

```text
C:\Gitrepos\evavo-local-image-generator
C:\Gitrepos\evavo-audio-studio
```

The configured command is an argument array, not a shell command:

```text
<python> <audio-studio>\worker_provider.py
  --request-json {request_json}
  --output-dir {output_dir}
  --task-id {task_id}
```

Audio Studio owns its own generation policy, models, rights/consent checks and output receipt. The gateway does not bypass those controls.

Useful overrides:

```text
EVAVO_AUDIO_STUDIO_DIR
EVAVO_AUDIO_PYTHON
EVAVO_AUDIO_PROVIDER_ARGV
EVAVO_AUDIO_PROVIDER_TIMEOUT
```

## 3D Studio worker

When `evavo-3d-studio` is a sibling checkout, the service manager may start its first-party token-gated execution worker on loopback. The default endpoint is:

```text
http://127.0.0.1:4314
```

Normal sibling layout:

```text
C:\Gitrepos\evavo-local-image-generator
C:\Gitrepos\evavo-3d-studio
C:\Gitrepos\evavo-3d-work
```

The managed worker is launched through the 3D Studio module entry point equivalent to:

```powershell
python -m evavo_3d_studio.agent_worker serve `
  --host 127.0.0.1 `
  --port 4314 `
  --workspace-root C:\Gitrepos\evavo-3d-work
```

The manager sets `EVAVO_3D_AGENT_EXECUTION_ENABLED=1` only in the managed worker/gateway environment. It never broadens the worker beyond its own candidate-production authority.

### Managed token

If no valid `EVAVO_3D_AGENT_EXECUTION_TOKEN` is supplied, the service manager can generate a cryptographically strong token and store it only in ignored local state:

```text
.evavo/gateway/3d-worker.token
```

A pre-existing worker is not adopted merely because its public health endpoint is reachable: the manager must prove the bearer token through a non-mutating authenticated probe and must know the worker workspace.

### Workspace and identity safety

The 3D workspace must remain outside the 3D Studio source tree. The manager refuses path escapes and refuses to replace an unknown process already occupying the configured worker port.

Managed shutdown only terminates a recorded 3D process when its command line still proves `evavo_3d_studio.agent_worker` + `serve`.

Useful overrides:

```text
EVAVO_3D_STUDIO_DIR
EVAVO_3D_PYTHON
EVAVO_3D_ENDPOINT
EVAVO_3D_AGENT_EXECUTION_TOKEN
EVAVO_3D_AGENT_WORKSPACE_ROOT
EVAVO_GATEWAY_MANAGE_3D
EVAVO_3D_PROVIDER_TIMEOUT
```

Set `EVAVO_GATEWAY_MANAGE_3D=0` to disable automatic first-party 3D worker management while leaving the core gateway available.

## Generic provider safety contract

A reviewed CLI provider must:

1. be configured as a JSON argument array;
2. run through `asyncio.create_subprocess_exec`, never `shell=True`;
3. receive task-local request/output paths;
4. emit a JSON object receipt;
5. report `"ok": true` for success;
6. identify a real artifact;
7. keep the artifact inside the admitted provider task workspace.

The runner bounds retained stdout/stderr and enforces timeouts. Process exit code `0` alone is not success.

## Failure behavior

Auxiliary POST routes return `202` when the task is accepted. If the provider is absent, misconfigured, times out, emits a bad receipt or produces an inadmissible artifact, the task transitions to `failed` with a structured error such as:

```text
PROVIDER_UNAVAILABLE
PROVIDER_CONFIG_INVALID
PROVIDER_FAILED
PROVIDER_PROTOCOL_ERROR
PROVIDER_OUTPUT_INVALID
PROVIDER_TIMEOUT
```

No fake artifact is created.

## Service manager

```powershell
python EVAVO-SERVICE-MANAGER.py start
python EVAVO-SERVICE-MANAGER.py health
python EVAVO-SERVICE-MANAGER.py monitor --interval 5
python EVAVO-SERVICE-MANAGER.py stop
```

Native ComfyUI plus the gateway itself remain the required pair for overall gateway health. Auxiliary readiness is informational/delegated and can be inspected through `/services` or `AGENT-STATUS.ps1`.

## Regression tests

The authoritative verifier now includes:

```text
test-gateway.py
tests/test_gateway_providers.py
tests/test_gateway_service_manager_providers.py
```

Run everything with:

```powershell
python evavo.py verify --full --require-powershell
```

Contract tests use isolated deterministic fixtures. Real GPU/model/provider readiness remains a workstation-level validation and is never inferred solely from these tests.
