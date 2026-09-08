# EVAVO Local Image Generator - Deployment Architecture

This document describes repository-backed behavior. Live workstation state is determined by `python evavo.py status`, not by this document.

## Native-first architecture

```text
Agent / Operator / MCP host
          |
          v
       evavo.py
          |
   +------+----------------+
   |                       |
   v                       v
generate-batch.py      monitor-evavo.py
   |
   v
evavo-wrapper.py
   |
   +-------------------------------+
   |                               |
   v                               v
Native ComfyUI                  EVAVO fallback
/system_stats                   /system
/object_info                    /api/status
/prompt                         /api/prompt
/history/{prompt_id}                 |
/view                                v
   |                         mock-comfyui-server.py
   |
   +---------------+---------------+
                   |
                   v
       downloaded images + task history
```

Selection order:

1. EVAVO compatibility endpoint when one is explicitly running.
2. Native ComfyUI at the configured endpoint.
3. Managed mock fallback only if no usable backend exists and `evavo.py start` is asked to start one.

A native ComfyUI process is externally owned. EVAVO does not kill or replace it.

## Real rendering contract

Native ComfyUI integration uses:

```text
GET  /system_stats
GET  /object_info/CheckpointLoaderSimple
POST /prompt
GET  /history/{prompt_id}
GET  /view
```

A queued native request returns ComfyUI's real `prompt_id`, used as the EVAVO `task_id`.

With wait/collection enabled, EVAVO polls history, enumerates image outputs, downloads them via `/view`, and returns concrete local file paths.

## Workflow support

Default graph uses built-in ComfyUI nodes suitable for conventional checkpoint pipelines:

```text
CheckpointLoaderSimple -> CLIPTextEncode -> KSampler -> VAEDecode -> SaveImage
```

For Flux, custom nodes, or specialist pipelines, configure an API-format workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Supported placeholders:

```text
{{prompt}} {{negative_prompt}} {{checkpoint}}
{{width}} {{height}} {{steps}} {{cfg_scale}}
{{seed}} {{filename_prefix}}
```

## Operational controller

```powershell
python evavo.py doctor
python evavo.py bootstrap
python evavo.py start
python evavo.py status
python evavo.py generate --prompts "test" --project smoke
python evavo.py tasks
python evavo.py stats
python evavo.py test
python evavo.py stop
```

For synchronous real output collection:

```powershell
python generate-batch.py --prompts "test" --project smoke --wait
```

## MCP agents

The stdio MCP server uses the current Python SDK v2 major line and is launched with:

```powershell
python -m evavo_local_image_generator.mcp_server
```

Exposed tools:

```text
health_check
list_checkpoints
generate_image
generation_status
collect_generation
```

The MCP `generate_image` tool waits for native output by default and returns downloaded paths.

## Test architecture

`python evavo.py test` launches isolated loopback simulators rather than using the operator's port 8188. Tests cover:

- compatibility-backend health and queueing;
- native ComfyUI detection;
- checkpoint discovery;
- standard API workflow submission;
- custom workflow template substitution;
- native prompt IDs and history parsing;
- `/view` output download;
- concurrent batch tracking;
- offline nonzero exit behavior;
- native backend preference;
- managed fallback lifecycle.

## State and output locations

```text
.evavo/operations-service.json   managed mock PID/state
.evavo/mock-service.log          managed mock log
.evavo/outputs/                  default downloaded images
task_history.json                durable task history
task_history.json.lock           inter-process lock
```

Logical wider-repository storage remains under `bee://` URIs. These are resource identifiers, not Windows filesystem paths.

## Security boundary

- Managed server is loopback-only.
- Native ComfyUI is expected to remain local unless separately secured.
- Request failures and malformed responses are explicit errors.
- Output files use atomic temporary writes.
- Native filenames are reduced to a basename locally to prevent traversal outside the configured download directory.
- Output downloads are size-capped.
- Task history is lock-protected and atomically replaced.
- Startup never broadly terminates `python.exe`.

## Verification

On the actual workstation, the authoritative deployment check is:

```powershell
python evavo.py bootstrap
python evavo.py status
python generate-batch.py --prompts "EVAVO smoke test" --project smoke --wait
```

If the backend is the managed mock, the smoke command will queue but cannot render a file. For a real image file, native ComfyUI must be running and have a usable checkpoint or configured custom workflow.
