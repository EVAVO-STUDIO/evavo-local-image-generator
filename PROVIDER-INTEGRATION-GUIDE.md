# EVAVO Unified Gateway Provider Integration

The Unified Gateway keeps the public ChatGPT/Claude HTTP contract stable while delegating generation to the Studio that owns each production pipeline.

## Stable public contract

The provider layer does **not** change these compatibility surfaces:

- Gateway: `127.0.0.1:8000`
- ComfyUI: `127.0.0.1:8188`
- Ollama: `127.0.0.1:11434`
- `GET /health` returns exactly `{"status":"healthy","gateway":"ok","comfyui":"ok"}` when ComfyUI is healthy.
- `POST /generate/image`
- `POST /generate/video`
- `POST /generate/audio`
- `POST /generate/3d`
- `GET /tasks`
- `GET /tasks/{task_id}/status`
- `GET /results/{task_id}`
- WebSocket `/ws/progress/{task_id}`
- task IDs retain `img_`, `vid_`, `aud_`, and `3d_` plus an integer timestamp.

`GET /services` is additive. Use it to inspect provider readiness without changing the strict `/health` contract.

## Image

Images continue to use the repository's native `ComfyUIBackend` against `EVAVO_COMFYUI_ENDPOINT` (default `http://127.0.0.1:8188`). No provider shim is inserted in the image path.

## Video Studio / Wan 2.1

By default the gateway discovers the reviewed worker at:

```text
../evavo-video-studio/tools/wan21_t2v_worker.py
```

Override Studio discovery when necessary:

```powershell
$env:EVAVO_VIDEO_STUDIO_DIR = "C:\GitRepos\evavo-video-studio"
```

Configure the reviewed local Wan snapshot:

```powershell
$env:EVAVO_WAN21_MODEL_DIR = "C:\AI\Wan2.1-T2V-1.3B-Diffusers"
```

The model directory must contain `evavo-model-manifest.json`. The gateway computes that manifest's SHA-256 before invoking the worker. For an independently pinned value, set:

```powershell
$env:EVAVO_WAN21_MODEL_MANIFEST_SHA256 = "<64 lowercase hex characters>"
```

If the pinned value differs from the local manifest, generation fails closed. The worker itself re-verifies the manifest and every model file before generation.

Optional controls:

```powershell
$env:EVAVO_VIDEO_PYTHON = "C:\GitRepos\evavo-video-studio\.venv\Scripts\python.exe"
$env:EVAVO_VIDEO_PROVIDER_TIMEOUT = "7200"
```

The gateway validates the worker JSON receipt, requires `ok: true`, verifies `video.mp4`, checks its SHA-256 against the receipt, and copies the admitted artifact into gateway results.

### Explicit video provider override

For a reviewed alternate local worker, set `EVAVO_VIDEO_PROVIDER_ARGV` to a JSON string array. Shell strings are deliberately unsupported.

```powershell
$env:EVAVO_VIDEO_PROVIDER_ARGV = '["python","C:\\tools\\video-worker.py","--request","{request_json}","--output-dir","{output_dir}"]'
```

Available placeholders are `{task_id}`, `{prompt}`, `{request_json}`, and `{output_dir}`. The command must emit a JSON object on its final JSON stdout line with `"ok": true` and an artifact path in `output`, `path`, `output_path`, or `file`.

## Audio Studio

Audio does not currently publish a production execution worker with a stable contract equivalent to Video Studio or 3D Studio. The gateway therefore fails closed instead of routing to the legacy placeholder generator.

A reviewed Audio Studio worker can be connected without changing `/generate/audio` by configuring a JSON argv array:

```powershell
$env:EVAVO_AUDIO_PROVIDER_ARGV = '["python","C:\\GitRepos\\evavo-audio-studio\\tools\\worker.py","--request","{request_json}","--output-dir","{output_dir}"]'
$env:EVAVO_AUDIO_PROVIDER_TIMEOUT = "900"
```

The same JSON receipt and output confinement rules used by configured video providers apply. Kokoro should remain on `127.0.0.1:8880` when used by an Audio Studio worker so it cannot collide with the fixed Gateway port `8000`.

## 3D Studio execution worker

The gateway integrates the existing token-gated 3D Studio agent worker on port `4314`. Start 3D Studio with its existing security boundary:

```powershell
$env:EVAVO_3D_AGENT_EXECUTION_ENABLED = "1"
$env:EVAVO_3D_AGENT_WORKSPACE_ROOT = "C:\EVAVO-3D-WORK"
$env:EVAVO_3D_AGENT_EXECUTION_TOKEN = "replace-with-at-least-32-random-characters"
evavo-3d-studio-worker serve --host 127.0.0.1 --port 4314
```

Optional endpoint override:

```powershell
$env:EVAVO_3D_ENDPOINT = "http://127.0.0.1:4314"
$env:EVAVO_3D_PROVIDER_TIMEOUT = "10800"
```

The gateway:

1. verifies `/api/v1/health` reports execution enabled;
2. verifies `pipeline.full-candidate` appears in `/api/v1/capabilities`;
3. asks the worker to compile the governed job rather than manufacturing its hash/version fields;
4. submits the compiled job with the bearer token;
5. polls the authenticated job status;
6. accepts only a completed execution receipt for the expected worker job ID;
7. reads the reviewed candidate artifact only from `result.webDelivery.delivery.path`;
8. requires the artifact to remain inside the admitted task workspace;
9. verifies its SHA-256 when supplied by the worker receipt;
10. copies the candidate GLB into the gateway result directory.

A caller may pass a complete strict `brief` object as an additive field. When only `prompt` is supplied, the gateway compiles a conservative `evavo_3d_asset_production_brief_v1` text brief with human review still required and no automatic approval/promotion authority.

## Security and resilience rules

Provider execution is deliberately narrower than arbitrary shell execution:

- CLI providers use exact argument arrays and `asyncio.create_subprocess_exec`; `shell=True` is never used.
- request JSON and provider output are isolated under the configured gateway state directory, by default `.evavo/gateway/provider-tasks/<task_id>`.
- generic provider artifacts must resolve inside that task directory.
- stdout/stderr are drained while only a bounded amount is retained.
- provider timeouts terminate the child and escalate to kill if necessary.
- exit code `0` alone is not success; a valid JSON success receipt and a real artifact are required.
- path traversal and symlink output escapes are rejected.
- 3D retains its own bearer token, loopback, workspace and authority controls.
- provider receipts are stored internally with task state but are not exposed in the normal public task-status projection.

## Readiness

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services | ConvertTo-Json -Depth 8
```

A provider being unavailable does not break API compatibility. The generate call still creates the normal queued task; that task then moves to `failed` with a structured provider error such as `PROVIDER_UNAVAILABLE`, `PROVIDER_FAILED`, `PROVIDER_PROTOCOL_ERROR`, `PROVIDER_OUTPUT_INVALID`, or `PROVIDER_TIMEOUT`.

## Validation

Provider adapter tests cover:

- configured Audio CLI success;
- configured Video CLI success;
- 3D worker compile/submit/poll/result flow;
- generated 3D brief contract basics;
- rejection of provider output paths outside the admitted task workspace.

The existing gateway smoke test remains the end-to-end check for the public HTTP/WebSocket image contract. Real GPU Video/3D generation must still be run on the Windows workstation because the models, CUDA runtime and local Studio services are intentionally local-only.
