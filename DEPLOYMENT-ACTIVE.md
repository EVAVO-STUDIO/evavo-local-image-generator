# EVAVO Local Image Generator - Deployment Architecture

This document describes the **repository-backed operational architecture**. Runtime health is verified with `python evavo.py status` or `python evavo.py test`; this file does not claim that a particular workstation process is currently running.

## Reproducible control plane

```text
┌──────────────────────────────────────────────────────────────┐
│                    Agent / Operator                          │
│          ChatGPT / Codex / Claude / PowerShell              │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │     evavo.py      │
                    │ unified control   │
                    └───────┬───────────┘
                            │
            ┌───────────────┼─────────────────┐
            │               │                 │
            ▼               ▼                 ▼
┌──────────────────┐ ┌────────────────┐ ┌─────────────────┐
│ monitor-evavo.py │ │generate-batch.py│ │task-tracker.py  │
│ health/status    │ │ async batching │ │ history/stats   │
└─────────┬────────┘ └───────┬────────┘ └────────┬────────┘
          │                  │                   │
          │                  ▼                   │
          │         ┌───────────────────┐         │
          └────────►│ evavo-wrapper.py  │         │
                    │ stable JSON CLI   │         │
                    └─────────┬─────────┘         │
                              │ HTTP               │
                              ▼                    │
               ┌────────────────────────────┐     │
               │ 127.0.0.1:8188             │     │
               │ /system                    │     │
               │ /api/status                │     │
               │ /api/prompt                │     │
               └─────────────┬──────────────┘     │
                             │                    │
                             ▼                    │
               ┌────────────────────────────┐     │
               │ mock-comfyui-server.py     │     │
               │ reproducible queue mock    │     │
               └────────────────────────────┘     │
                                                  │
                    ┌─────────────────────────────┘
                    ▼
            ┌──────────────────────┐
            │ task_history.json    │
            │ lock + atomic writes │
            └──────────────────────┘
```

## Runtime components

### Unified controller: `evavo.py`

Purpose:

- start the managed mock service;
- wait for readiness;
- write PID/log metadata under `.evavo/`;
- check status;
- delegate generation/task commands;
- stop the managed service;
- run operational integration tests.

Primary commands:

```powershell
python evavo.py start
python evavo.py status
python evavo.py generate --examples
python evavo.py tasks
python evavo.py stats
python evavo.py test
python evavo.py stop
```

### Mock ComfyUI service: `mock-comfyui-server.py`

- Binds to `127.0.0.1:8188` by default.
- Refuses non-loopback binds.
- Implements `/system`, `/api/status`, and `/api/prompt`.
- Generates unique `evavo_<uuid>` task IDs.
- Uses `ThreadingHTTPServer` so health/status requests are not blocked by another connection.
- Caps request bodies at 1 MiB.
- Validates prompt/project shape.

This component is a deterministic local queue mock, not a real image renderer. A production ComfyUI bridge should preserve the same health and queue contract.

### Wrapper: `evavo-wrapper.py`

- Uses the shared HTTP/health contract in `evavo_operations.py`.
- Emits exactly one JSON object on stdout.
- Supports the existing commands:

```powershell
python evavo-wrapper.py health_check "{}"
python evavo-wrapper.py generate_image '{"prompt":"example","project_name":"demo"}'
```

- Rejects malformed arguments.
- Requires a valid queued `task_id` before reporting success.

### Batch generation: `generate-batch.py`

- Runs a service identity/readiness preflight by default.
- Uses `asyncio.create_subprocess_exec` for real concurrent wrapper execution.
- Bounds concurrency (default `4`).
- Handles per-task timeout/process/JSON/protocol failures.
- Returns a formatted table or `--json` output.
- Persists success and failure records through the shared tracker.
- Exits `1` on partial batch failure and `3` when preflight fails.

### Monitor: `monitor-evavo.py`

- Checks `/system` directly with HTTP status + JSON validation.
- Verifies service identity and protocol version.
- Independently exercises `evavo-wrapper.py health_check`.
- Runs both checks concurrently.
- Supports one-shot, continuous display, and continuous JSON-lines modes.
- Returns nonzero for degraded/offline one-shot checks.

### Task tracker: `task-tracker.py`

Persistence is provided by `evavo_operations.TaskTracker`:

- repository-relative default history file;
- configurable `EVAVO_TASK_HISTORY` path;
- inter-process advisory lock;
- atomic temp-file + `os.replace()` writes;
- explicit corruption/read errors instead of silently discarding history;
- normalized statuses (`queued`, `running`, `completed`, `failed`, `cancelled`, `unknown`);
- list/stats/add/update/clear CLI operations.

## Service contract

A healthy `/system` response contains:

```json
{
  "service": "evavo-local-image-generator",
  "protocol_version": 1,
  "status": "ready"
}
```

A successful queue response contains:

```json
{
  "status": "queued",
  "task_id": "evavo_<unique-id>"
}
```

Utilities do not treat simple TCP connectivity or arbitrary HTTP 200 responses as proof of health.

## Storage

Logical storage root used by package tooling:

```text
bee://primary/EVAVO/ImageGeneration/
```

`bee://` is treated as a resource URI, not a Windows path. Translation to filesystem/NAS locations belongs in the storage layer.

Operational task history defaults to:

```text
<repository>/task_history.json
```

Managed service state:

```text
<repository>/.evavo/operations-service.json
<repository>/.evavo/mock-service.log
```

## Environment

Supported Python runtime:

```text
Python 3.10+
```

Operational scripts require only the standard library. Wider repository dependencies remain documented in `requirements.txt`.

Environment variables:

```text
COMFYUI_ENDPOINT=http://127.0.0.1:8188
EVAVO_TASK_HISTORY=<optional custom JSON path>
EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE=bee://primary/EVAVO/ImageGeneration
```

## Windows startup

`START-EVAVO-SERVICES.bat` is repository-relative and safe against broad Python process termination. It:

- prefers `.venv\Scripts\python.exe`;
- checks required files;
- examines the process listening on port 8188;
- terminates it only when it is the EVAVO mock server;
- refuses unrelated port conflicts;
- performs a 20-attempt readiness loop with the real monitor;
- exits nonzero on failure.

For agent automation, prefer `python evavo.py start` because it records managed process state and logs without requiring CMD-specific behavior.

## Validation gates

Operational readiness should be established by running:

```powershell
python evavo.py test
```

The suite validates wrapper health, generation task IDs, monitor output, batch-to-tracker integration and offline failure behavior against an isolated mock port.

A deployment should not be described as active solely because this Markdown file exists; `evavo.py status` is the source of truth for live process state.

## Security boundary

Current mock service is deliberately local-only. Loopback reduces exposure but is not authentication. Before binding a real backend outside localhost, add authentication/authorization, restrict firewall access, validate all file/URI targets, limit payload sizes and avoid logging secrets.
