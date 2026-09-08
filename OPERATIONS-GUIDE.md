# EVAVO Local Image Generator - Operations Guide

Supported runtime: **Python 3.10+**. The local lifecycle/batch/monitor/tracker code uses the standard library. Install root `requirements.txt` for MCP and the wider repository.

## Canonical workstation workflow

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
python -m pip install -r requirements.txt
python evavo.py bootstrap
```

`bootstrap` performs:

```text
fast-forward main
  -> doctor
  -> isolated integration tests
  -> select/start backend
  -> final status
```

It refuses to overwrite a dirty worktree.

## Runtime architecture

```text
Human / ChatGPT / Codex / Claude / MCP host
                |
                v
            evavo.py
                |
       +--------+---------+
       |                  |
       v                  v
generate-batch.py   monitor-evavo.py
       |
       v
 evavo-wrapper.py
       |
       +-------------------------------+
       |                               |
       v                               v
EVAVO compatibility API          Native ComfyUI
/system                          /system_stats
/api/prompt                      /object_info
/api/status                      /prompt
                                 /history/{id}
                                 /view
       |                               |
       +---------------+---------------+
                       |
                       v
                 task_history.json
```

Native ComfyUI is preferred automatically. The managed mock is only a deterministic fallback/test service.

## Real ComfyUI rendering

Start ComfyUI normally on `127.0.0.1:8188`, then:

```powershell
python evavo.py status
python generate-batch.py --prompts "test image" --project smoke --wait
```

For native ComfyUI, EVAVO:

1. reads `/system_stats`;
2. discovers checkpoints via `/object_info/CheckpointLoaderSimple`;
3. builds or loads API-format workflow JSON;
4. submits `/prompt`;
5. receives `prompt_id`;
6. polls `/history/{prompt_id}`;
7. discovers `SaveImage` outputs;
8. downloads each file via `/view`;
9. atomically writes the local output file;
10. records status in task history.

Default download directory:

```text
<repo>/.evavo/outputs/
```

Custom directory:

```powershell
python generate-batch.py --prompts "test" --wait --output-dir "D:\EVAVO\Generated"
```

## Built-in workflow

The default workflow uses standard nodes:

```text
CheckpointLoaderSimple
CLIPTextEncode (positive)
CLIPTextEncode (negative)
EmptyLatentImage
KSampler
VAEDecode
SaveImage
```

Choose a checkpoint explicitly when required:

```powershell
$env:EVAVO_COMFYUI_CHECKPOINT = "model.safetensors"
```

If unset, the first checkpoint reported by `CheckpointLoaderSimple` is selected.

## Flux/custom workflows

Export the desired ComfyUI workflow in API format and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

or:

```powershell
python generate-batch.py --prompts "test" --workflow "D:\EVAVO\workflows\production-api.json" --wait
```

Template placeholders:

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

Exact placeholder values preserve their numeric type where appropriate.

## Queue vs wait

Fast asynchronous queueing:

```powershell
python evavo.py generate --prompts "one" "two" --project demo
```

Wait for concrete files:

```powershell
python generate-batch.py --prompts "one" "two" --project demo --wait --concurrency 2
```

Machine-readable:

```powershell
python generate-batch.py --prompts "one" --wait --json
```

## Existing task collection

```powershell
python evavo-wrapper.py task_status "{\"task_id\":\"<prompt-id>\"}"
python evavo-wrapper.py wait_image "{\"task_id\":\"<prompt-id>\",\"wait_timeout\":600}"
```

## Health and diagnostics

```powershell
python evavo.py doctor
python evavo.py status
python monitor-evavo.py --json
python monitor-evavo.py --continuous --interval 10
```

A healthy backend must be either:

- an EVAVO compatibility service with the expected service/protocol identity; or
- native ComfyUI responding to `/system_stats`.

Native ComfyUI is externally owned. `evavo.py stop` only stops an EVAVO mock process recorded in `.evavo/operations-service.json`.

## Tests

```powershell
python evavo.py test
```

The isolated suite validates both backend modes, including:

- health detection;
- native checkpoint discovery;
- API workflow queueing;
- prompt IDs;
- history parsing;
- native output download;
- custom workflow substitution;
- batch task persistence;
- offline exit behavior;
- native backend preference;
- managed mock lifecycle.

## MCP agents

Install:

```powershell
python -m pip install -r requirements.txt
```

Run stdio server:

```powershell
python -m evavo_local_image_generator.mcp_server
```

Available real tools:

```text
health_check
list_checkpoints
generate_image
generation_status
collect_generation
```

The repository pins the current MCP SDK major line to `mcp>=2,<3`. `generate_image` waits and returns downloaded file paths by default for MCP callers.

## Task persistence

```powershell
python evavo.py tasks
python evavo.py stats
python task-tracker.py list --project demo --json
```

`task_history.json` uses an inter-process lock and atomic temp-file replacement. A corrupt JSON history is reported instead of silently discarded.

Override location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\task_history.json"
```

## Security and failure handling

- Managed test/fallback service is loopback-only.
- Output downloads are capped (256 MiB/file by default).
- Downloaded filenames are reduced to a basename before local writing; remote subfolder data cannot escape the configured output directory.
- Writes use temporary files and `os.replace()` so interrupted downloads do not become finished outputs.
- HTTP and wrapper failures use nonzero exit codes.
- Startup does not kill arbitrary Python processes.
- Real ComfyUI is never stopped/replaced merely because EVAVO sees it on port 8188.
- A custom workflow is read only from the explicitly configured local file.

## Windows-specific recovery

If the checkout still contains the old `660298f` scripts:

```powershell
git pull --ff-only origin main
python -m pip install -r requirements.txt
python evavo.py bootstrap --skip-pull
```

Python 3.10+ includes `asyncio`; do not install the separate PyPI package. If it was installed, `python evavo.py doctor` reports whether it is shadowing the standard-library module.

Do not run:

```text
taskkill /IM python.exe
```

as a generic restart strategy.

## Important environment variables

| Variable | Purpose |
|---|---|
| `COMFYUI_ENDPOINT` | default operations endpoint |
| `EVAVO_COMFYUI_ENDPOINT` | native backend endpoint |
| `EVAVO_COMFYUI_CHECKPOINT` | preferred standard checkpoint |
| `EVAVO_COMFYUI_WORKFLOW` | custom API workflow template |
| `EVAVO_GENERATION_OUTPUT_DIR` | MCP default downloaded-output root |
| `EVAVO_TASK_HISTORY` | task-history JSON path |
| `EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE` | logical `bee://` storage root |

`bee://` values remain logical storage URIs, not paths to concatenate directly with Windows filesystem strings.
