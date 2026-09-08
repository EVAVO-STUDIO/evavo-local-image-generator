# EVAVO Local Image Generator

Local-first image generation and automation for EVAVO Studio. The repository now provides one operational path for humans, Python automation, and MCP agents, with **native ComfyUI preferred automatically** and a deterministic mock backend available for testing/fallback.

## What is real

- Native ComfyUI detection through `/system_stats`.
- Checkpoint discovery through `/object_info/CheckpointLoaderSimple`.
- API-format workflow submission through `/prompt`.
- Prompt status/output discovery through `/history/{prompt_id}`.
- Image collection through `/view`.
- Built-in standard txt2img workflow using normal ComfyUI nodes.
- Custom API-workflow templates for Flux/custom-node/other pipelines.
- Bounded concurrent batch queueing.
- Optional wait-until-complete + automatic file download.
- Durable lock-protected task history.
- Python lifecycle/health/bootstrap controller.
- MCP Python SDK v2 stdio tools for agents.
- Mock/native simulation integration tests.

The managed mock service is a queue/API simulator used when real ComfyUI is not running. It is not presented as a renderer.

## Requirements

- Python 3.10+
- A local ComfyUI instance for real rendering, normally at `http://127.0.0.1:8188`
- At least one compatible model/checkpoint or a custom ComfyUI API workflow

Install the full repository dependencies:

```powershell
python -m pip install -r requirements.txt
```

Do not install the PyPI package named `asyncio`; supported Python versions already include `asyncio` in the standard library.

## First run on Windows

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
python -m pip install -r requirements.txt
python evavo.py doctor
python evavo.py test
python evavo.py start
python evavo.py status
```

Or use the automated controller:

```powershell
python evavo.py bootstrap
```

`bootstrap` fast-forwards `main`, runs diagnostics/tests, uses an already-running native ComfyUI when available, otherwise starts the managed mock fallback, and verifies the final backend health.

## Generate images

Queue work without waiting:

```powershell
python evavo.py generate --prompts "cinematic industrial harbour at night" --project harbour
```

For a real ComfyUI render and downloaded output:

```powershell
python generate-batch.py --prompts "cinematic industrial harbour at night" --project harbour --wait
```

Default downloaded native outputs are written below:

```text
.evavo/outputs/
```

Choose another directory:

```powershell
python generate-batch.py --prompts "PS1 survival horror corridor" --project ps1 --wait --output-dir "C:\EVAVO\Generated"
```

Machine-readable output:

```powershell
python generate-batch.py --prompts "test image" --wait --json
```

## Backend selection

The operational tools try the endpoint in this order:

1. EVAVO compatibility service (`/system`).
2. Native ComfyUI (`/system_stats`).
3. If `evavo.py start` finds neither, it starts the managed mock fallback.

A running native ComfyUI is never killed or replaced by the mock.

Configure another local endpoint:

```powershell
$env:COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
$env:EVAVO_COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
```

## Checkpoints

When using the built-in workflow, EVAVO reads checkpoints from ComfyUI's `CheckpointLoaderSimple` node. It uses `EVAVO_COMFYUI_CHECKPOINT` when set, otherwise the first reported checkpoint.

```powershell
$env:EVAVO_COMFYUI_CHECKPOINT = "your-model.safetensors"
```

The built-in graph is intended for conventional checkpoint pipelines that work with:

- `CheckpointLoaderSimple`
- `CLIPTextEncode`
- `EmptyLatentImage`
- `KSampler`
- `VAEDecode`
- `SaveImage`

## Custom ComfyUI workflow templates

For Flux, custom nodes, specialist models, or any graph that does not fit the built-in workflow, export a workflow in **ComfyUI API format** and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\EVAVO\workflows\my-api-workflow.json"
```

Or per command:

```powershell
python generate-batch.py --prompts "my prompt" --workflow "C:\EVAVO\workflows\my-api-workflow.json" --wait
```

Supported template placeholders are recursively replaced:

```text
{{prompt}}
{{negative_prompt}}
{{checkpoint}}
{{width}}
{{height}}
{{steps}}
{{cfg_scale}}
{{seed}}
{{filename_prefix}}
```

When a JSON value is exactly a placeholder, numeric replacements remain numeric rather than becoming strings.

## Wrapper API

Health:

```powershell
python evavo-wrapper.py health_check "{}"
```

Queue:

```powershell
python evavo-wrapper.py generate_image "{\"prompt\":\"test\",\"project_name\":\"demo\"}"
```

Queue, wait, and download:

```powershell
python evavo-wrapper.py generate_image "{\"prompt\":\"test\",\"project_name\":\"demo\",\"wait\":true}"
```

Status:

```powershell
python evavo-wrapper.py task_status "{\"task_id\":\"<prompt-id>\"}"
```

Wait/collect an existing prompt:

```powershell
python evavo-wrapper.py wait_image "{\"task_id\":\"<prompt-id>\",\"wait_timeout\":600}"
```

Wrapper stdout is exactly one JSON object so agents can consume it safely.

## Task history

```powershell
python evavo.py tasks
python evavo.py stats
python task-tracker.py list --project demo --json
```

History defaults to `task_history.json`. Writes use an inter-process lock and atomic replacement.

## MCP agent integration

The repository uses the current MCP Python SDK v2 line (`mcp>=2,<3`). `.mcp.json` launches:

```text
python -m evavo_local_image_generator.mcp_server
```

The server exposes real tools:

- `health_check`
- `list_checkpoints`
- `generate_image`
- `generation_status`
- `collect_generation`

`generate_image` waits for the rendered image by default for agent callers and returns concrete downloaded file paths. Unsupported video/audio/3D modes are not falsely advertised as completed or queued.

## Programmatic Python

```python
import asyncio
from evavo_local_image_generator.scripts.generate import generate_images

results = asyncio.run(
    generate_images(
        ["a storm over a 1990s industrial city"],
        output_project="demo",
        width=768,
        height=512,
        steps=24,
    )
)

print(results)
```

This path submits real native ComfyUI work; it no longer fabricates queue IDs.

## Validation

Run:

```powershell
python evavo.py test
```

The integration suite exercises isolated loopback services and verifies:

- EVAVO mock health/queue behavior;
- native ComfyUI detection;
- checkpoint discovery;
- standard workflow submission;
- native prompt IDs;
- history/output parsing;
- `/view` file download;
- custom workflow substitution;
- concurrent batch tracking;
- offline failure exit codes;
- native-backend preference;
- managed mock `start -> status -> stop` lifecycle.

## Security baseline

- Managed services bind to loopback only.
- Native output downloads are capped at 256 MiB per file by default.
- Download destinations use a sanitized basename, preventing ComfyUI filenames from escaping the configured local output directory.
- Task history uses locking and atomic replacement.
- Startup never performs broad `taskkill /IM python.exe` termination.
- Native ComfyUI is treated as externally owned; `evavo.py stop` stops only the mock process that EVAVO itself started.

## Main operational files

```text
evavo.py                                  unified lifecycle/controller
evavo-wrapper.py                          stable JSON wrapper
evavo_operations.py                       HTTP + task primitives
generate-batch.py                         concurrent generation / optional wait
monitor-evavo.py                          mock/native backend health
task-tracker.py                           durable task history CLI
mock-comfyui-server.py                    deterministic test/fallback simulator
test-operations.py                        end-to-end operational tests
evavo_local_image_generator/backends/
  comfyui_backend.py                      native ComfyUI implementation
evavo_local_image_generator/mcp_server.py MCP v2 stdio agent server
```

See `OPERATIONS-GUIDE.md` and `QUICK-REFERENCE.md` for operational commands and recovery guidance.
