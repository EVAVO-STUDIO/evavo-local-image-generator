# EVAVO Gateway Auxiliary Providers

The Unified Gateway keeps native ComfyUI as its required image renderer while routing other media to first-party sibling studios when their verified execution surfaces are available.

The public compatibility contract is unchanged: Gateway stays on port `8000`, ComfyUI stays on `8188`, healthy `/health` remains exactly `{"status":"healthy","gateway":"ok","comfyui":"ok"}`, existing generation/task/result paths remain stable, task IDs retain their existing prefix/timestamp format, CORS remains enabled, and the WebSocket progress path is unchanged.

## Audio Studio

When `evavo-audio-studio` is a sibling checkout and contains `worker_provider.py`, `START-GATEWAY.ps1` and `EVAVO-SERVICE-MANAGER.py` automatically configure the existing JSON-argv provider boundary. An explicit `EVAVO_AUDIO_PROVIDER_ARGV` always wins.

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

Audio Studio owns generation policy and model routing. The adapter supports its governed music, SFX and MIDI generation path, plus its separately governed Qwen3-TTS consented voice-clone path when the caller supplies the required immutable-model and voice-consent evidence. The gateway does not bypass those controls.

Useful overrides:

```text
EVAVO_AUDIO_STUDIO_DIR
EVAVO_AUDIO_PYTHON
EVAVO_AUDIO_PROVIDER_ARGV
EVAVO_AUDIO_PROVIDER_TIMEOUT
```

## 3D Studio worker

When `evavo-3d-studio` is a sibling checkout, the service manager may start its first-party token-gated execution worker on loopback. The default endpoint remains:

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

The manager sets `EVAVO_3D_AGENT_EXECUTION_ENABLED=1` only for the managed worker/gateway process environment. It never broadens the worker beyond its native candidate-production authority.

### Managed token

If no valid `EVAVO_3D_AGENT_EXECUTION_TOKEN` is already supplied, the manager generates a cryptographically strong token and stores it in ignored local gateway state:

```text
.evavo/gateway/3d-worker.token
```

The token is retained across normal restarts but is never committed. A pre-existing worker is not adopted merely because its public health endpoint is reachable: the manager must prove the bearer token through a non-mutating authenticated job-status probe and must know the worker workspace. Unknown or stale credentials fail closed.

### Workspace and identity safety

The 3D workspace must be outside the 3D Studio source tree. The manager refuses path escapes and refuses to replace an unknown service already occupying the configured worker port.

Managed shutdown only terminates a recorded 3D process when its command line still proves both `evavo_3d_studio.agent_worker` and `serve`. It does not kill arbitrary Python processes.

Useful overrides:

```text
EVAVO_3D_STUDIO_DIR
EVAVO_3D_PYTHON
EVAVO_3D_ENDPOINT
EVAVO_3D_AGENT_EXECUTION_TOKEN
EVAVO_3D_AGENT_WORKSPACE_ROOT
EVAVO_GATEWAY_MANAGE_3D
```

Set `EVAVO_GATEWAY_MANAGE_3D=0` to disable automatic worker management while leaving the rest of the gateway stack available.

## Service manager behavior

```powershell
python EVAVO-SERVICE-MANAGER.py start
python EVAVO-SERVICE-MANAGER.py health
python EVAVO-SERVICE-MANAGER.py monitor --interval 5
python EVAVO-SERVICE-MANAGER.py stop
```

Audio and 3D are auxiliary providers. Their unavailability is reported in service-manager health/status without changing the required image-gateway healthy contract. Native ComfyUI plus the gateway itself remain the required pair for overall compatibility health.

`monitor` restores native ComfyUI and the gateway as before. When a discoverable 3D Studio checkout is present, it also attempts to restore the managed 3D worker without forcefully replacing unknown port occupants.

## Regression tests

The repository includes provider-orchestration tests covering:

- loopback endpoint restrictions;
- sibling Audio Studio JSON-argv discovery;
- strong managed 3D token generation and reuse;
- first-party 3D worker identity and token proof;
- refusal to adopt an unknown pre-existing worker.

Run the focused suite with:

```powershell
python -m unittest tests.test_gateway_service_manager_providers -v
```

These tests use an isolated deterministic worker fixture. Real GPU/model readiness remains a workstation-level validation and is not inferred from the contract tests.
