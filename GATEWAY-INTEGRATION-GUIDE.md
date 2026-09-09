# EVAVO Unified Gateway Integration Guide

The EVAVO Unified Gateway is a stable local HTTP compatibility layer for ChatGPT, Claude, MCP adapters, scripts, and other agents. It deliberately keeps the public API small and fixed while allowing the internal generation backends to evolve.

## Fixed compatibility contract

Do not rename or remove these routes:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Gateway + ComfyUI readiness |
| `POST` | `/generate/image` | Queue image generation |
| `POST` | `/generate/video` | Queue video generation |
| `POST` | `/generate/audio` | Queue audio generation |
| `POST` | `/generate/3d` | Queue 3D generation |
| `GET` | `/tasks` | List tasks |
| `GET` | `/tasks/{task_id}/status` | Read one task |
| `GET` | `/results/{task_id}` | Download the primary result |
| `WS` | `/ws/progress/{task_id}` | Receive task progress events |

Ports that are part of the compatibility contract:

- EVAVO Gateway: `127.0.0.1:8000`
- ComfyUI: `127.0.0.1:8188`
- Ollama: `127.0.0.1:11434`

A healthy gateway returns exactly:

```json
{"status":"healthy","gateway":"ok","comfyui":"ok"}
```

Image task IDs retain the `img_<timestamp>` form. Other additive modalities use `vid_<timestamp>`, `aud_<timestamp>`, and `3d_<timestamp>`.

## Important port note: Kokoro

Older EVAVO audio code used port `8000` for Kokoro. That conflicts with the fixed Gateway port and two processes cannot bind the same host/port. The Gateway remains on `8000`. Use `EVAVO_KOKORO_ENDPOINT=http://127.0.0.1:8880` for Kokoro (or another free port). `START-GATEWAY.ps1` sets `8880` as the safe default without changing the Gateway contract.

## Installation

From the repository root on Windows:

```powershell
Set-Location C:\Gitrepos\evavo-local-image-generator
python --version
python -m pip install -r requirements.txt
python -c "import fastapi, uvicorn, pydantic, aiohttp, websockets; print('All imports OK')"
```

Python 3.10 or newer is required.

## Start and stop

Recommended monitored mode:

```powershell
python EVAVO-SERVICE-MANAGER.py monitor --interval 5
```

Start once in the background:

```powershell
python EVAVO-SERVICE-MANAGER.py start
```

Stop only EVAVO-managed processes:

```powershell
python EVAVO-SERVICE-MANAGER.py stop
```

Health/status:

```powershell
python EVAVO-SERVICE-MANAGER.py health
curl.exe http://127.0.0.1:8000/health
```

Or use the convenience launcher:

```powershell
.\START-GATEWAY.ps1
.\START-GATEWAY.ps1 -Monitor -Interval 5
```

The service manager first reuses a healthy existing ComfyUI. If ComfyUI is offline it asks the repository's hardened native ComfyUI runtime to discover/start a real installation. If that is unavailable, the deterministic repository mock is allowed as a validation fallback by default. Set `EVAVO_GATEWAY_ALLOW_MOCK_COMFYUI=0` to require a real ComfyUI installation.

## Image generation

Queue a task:

```powershell
curl.exe -X POST http://127.0.0.1:8000/generate/image `
  -H "Content-Type: application/json" `
  -d '{"prompt":"a beautiful sunset over mountains"}'
```

Stable queue response:

```json
{"task_id":"img_1694208847","status":"queued","progress":0}
```

Optional image fields are additive and include the existing ComfyUI adapter controls such as `project_name`, `negative_prompt`, `width`, `height`, `steps`, `cfg_scale`, `seed`, `checkpoint`, `workflow_path`, and `wait_timeout`.

Check status:

```powershell
curl.exe http://127.0.0.1:8000/tasks/img_1694208847/status
```

Download when complete:

```powershell
curl.exe http://127.0.0.1:8000/results/img_1694208847 --output result.png
```

If the task is still running, `/results/{task_id}` returns HTTP `202` with JSON status. A failed task returns HTTP `409` with its error code and message.

## Real-time progress

Connect to:

```text
ws://127.0.0.1:8000/ws/progress/{task_id}
```

The socket emits the public task record whenever it changes and closes after `completed`, `failed`, or `cancelled`.

## API documentation

FastAPI serves interactive docs at:

```text
http://127.0.0.1:8000/docs
```

OpenAPI JSON is available at:

```text
http://127.0.0.1:8000/openapi.json
```

## ChatGPT compatibility

Any ChatGPT integration capable of reaching the local/tunneled gateway can use the OpenAPI document. The gateway keeps CORS enabled and does not require a ChatGPT-specific request format.

Conceptual plugin metadata:

```json
{
  "schema_version": "1.0.0",
  "name_for_human": "EVAVO Unified Generator",
  "name_for_model": "evavo_generator",
  "description_for_human": "Generate media through the EVAVO local gateway",
  "description_for_model": "Use the EVAVO Gateway API for local generation tasks",
  "auth": {"type": "none"},
  "api": {"type": "openapi", "url": "http://127.0.0.1:8000/openapi.json"}
}
```

For remote ChatGPT access, use the repository's secure ChatGPT MCP/tunnel tooling rather than exposing port 8000 directly to the public Internet.

## Claude compatibility

Claude-side code can call the same stable REST API:

```python
import aiohttp

async def generate_image(prompt: str, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:8000/generate/image",
            json={"prompt": prompt, **kwargs},
        ) as response:
            response.raise_for_status()
            return await response.json()
```

The existing EVAVO MCP server remains independent and is not removed or renamed by the gateway.

## Persistence and restart behaviour

Gateway task state is atomically persisted at:

```text
evavo-state/gateway_tasks.json
```

Generated files are stored under:

```text
evavo-state/results/<task_id>/
```

The shared `TaskTracker` is updated on a best-effort basis as a compatibility mirror. After a Gateway process restart, any task that was only `queued` or `running` is marked failed with `GATEWAY_RESTARTED` rather than being falsely reported as still active.

## Automated verification

Run the end-to-end smoke test after startup:

```powershell
python gateway-smoke-test.py
```

It verifies:

- exact `/health` contract
- required OpenAPI paths
- image task queue response and ID format
- WebSocket progress
- task status polling
- result download
- HTTP latency measurements

The test exits non-zero on failure and prints a machine-readable JSON report, making it suitable for ChatGPT, Claude, Codex, or local automation.

## Troubleshooting

### Port 8000 already in use

```powershell
netstat -ano | findstr :8000
```

Do not move the Gateway. Move the conflicting service. For Kokoro, port `8880` is recommended.

### ComfyUI not responding

```powershell
curl.exe http://127.0.0.1:8188/system_stats
python EVAVO-SERVICE-MANAGER.py health
```

The service manager will not kill an unknown process occupying 8188.

### Dependencies missing

```powershell
python -m pip install -r requirements.txt
```

### Task history unavailable

Check write permissions for `evavo-state/` and the existing shared task history. Gateway state writes use an atomic temporary-file replacement to reduce corruption risk.

### Gateway logs

EVAVO-managed process logs are written under:

```text
evavo-state/logs/
```

## Cross-AI change rules

Safe changes include internal refactoring, additional endpoints, better logging, stronger persistence, improved backend adapters, and performance improvements.

Do not change existing endpoint paths/methods, request field names, the image queue response field names, Gateway/ComfyUI/Ollama ports, the `img_<timestamp>` task ID form, the healthy `/health` payload, the WebSocket path, or CORS availability without a coordinated API version migration.
