# EVAVO Local Image Generator - Operations Guide

This guide describes the repository's actual local operational control plane. The supported runtime is **Python 3.10+**. The operational scripts use only the Python standard library; install `requirements.txt` for the wider generator/tooling repository.

## Recommended workflow

The preferred entry point for humans and agents is `evavo.py`:

```powershell
python evavo.py start
python evavo.py status
python evavo.py generate --prompts "sunset landscape" "cyberpunk city" --project demo
python evavo.py tasks --limit 20
python evavo.py stats
python evavo.py stop
```

`START-EVAVO-SERVICES.bat` remains available for Windows operators who prefer a batch launcher.

## Architecture

```text
Agent / operator
      |
      v
   evavo.py
      |
      +------------------------------+
      |                              |
      v                              v
monitor-evavo.py              generate-batch.py
      |                              |
      |                       async wrapper processes
      |                              |
      +-----------> evavo-wrapper.py +
                         |
                         v
                http://127.0.0.1:8188
                   /system
                   /api/status
                   /api/prompt
                         |
                         v
                mock-comfyui-server.py

All generation results ----------> task_history.json
                                  atomic + lock protected
```

The mock server is a reproducible local queue/API surface. It is not a real image renderer. Replace the mock HTTP implementation with the real ComfyUI-compatible backend when connecting production generation, while preserving the same wrapper/health contract.

## Quick start

### 1. Verify Python

```powershell
python --version
```

Python 3.10 or newer is required.

Optional virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The operational control plane itself does not need third-party packages.

### 2. Start services

Preferred:

```powershell
python evavo.py start
```

Windows batch alternative:

```batch
START-EVAVO-SERVICES.bat
```

The managed Python controller writes service state and logs below `.evavo/`.

### 3. Verify health

```powershell
python evavo.py status
python monitor-evavo.py --json
```

A healthy service must:

- respond with HTTP 2xx;
- return valid JSON;
- identify itself as `evavo-local-image-generator`;
- report protocol version `1`;
- report `ready`/`ok` health state;
- pass the wrapper health check.

A one-shot monitor exits nonzero when degraded/offline, making it safe for automation.

### 4. Queue image tasks

```powershell
python evavo.py generate --prompts "landscape" "portrait" "abstract" --project production_batch
```

Examples:

```powershell
python evavo.py generate --examples
python generate-batch.py --examples
python generate-batch.py --prompts "prompt one" "prompt two" --concurrency 4 --json
```

`generate-batch.py` performs a service preflight by default, queues requests concurrently using async subprocesses, validates returned task IDs and writes every result to task history.

Concurrency is bounded with `--concurrency` (default `4`, allowed `1..64`).

### 5. Inspect tasks

```powershell
python evavo.py tasks
python evavo.py tasks --limit 100 --project production_batch
python evavo.py stats
```

Direct tracker commands:

```powershell
python task-tracker.py list --limit 50
python task-tracker.py list --project production_batch --json
python task-tracker.py stats --json
python task-tracker.py update <TASK_ID> completed --output-uri "bee://primary/EVAVO/ImageGeneration/outputs/example.png"
```

Task history defaults to:

```text
<repository>\task_history.json
```

Override with:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\task_history.json"
```

Writes use an inter-process lock and atomic replacement to avoid lost updates/truncated JSON during concurrent operation.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `COMFYUI_ENDPOINT` | `http://127.0.0.1:8188` | Service base URL |
| `EVAVO_TASK_HISTORY` | `<repo>/task_history.json` | Persistent task history location |
| `EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE` | `bee://primary/EVAVO/ImageGeneration` | Logical storage root used by package tooling |

## `bee://` storage

`bee://` values are logical resource URIs, not Windows filesystem paths. They should be resolved by the storage layer rather than concatenated directly with `C:\...` paths. Keep path/URI translation centralized and reject traversal outside configured storage roots.

## Monitoring

Single health check:

```powershell
python monitor-evavo.py
```

Machine-readable:

```powershell
python monitor-evavo.py --json
```

Continuous human display:

```powershell
python monitor-evavo.py --continuous --interval 10
```

Continuous JSON lines for agents/log collectors:

```powershell
python monitor-evavo.py --continuous --interval 10 --json
```

## Exit codes

Operational scripts use conventional nonzero exit codes rather than silently reporting success:

| Code | Meaning |
|---:|---|
| `0` | Requested operation succeeded |
| `1` | General or partial operation failure |
| `2` | Invalid CLI/configuration/prerequisite |
| `3` | Service/wrapper unavailable or degraded |
| `4` | Task not found (tracker update) |
| `5` | Windows startup port conflict with a non-EVAVO process |

Do not rely on historical `127`/`255` values from the old quick reference.

## Windows startup behavior

`START-EVAVO-SERVICES.bat`:

1. resolves the repository directory with `%~dp0`;
2. prefers `.venv\Scripts\python.exe` when present;
3. verifies required runtime files;
4. checks port `8188`;
5. only terminates the existing listener when its command line identifies the EVAVO mock server;
6. refuses to kill unrelated processes using the port;
7. starts the service in a minimized window;
8. runs up to 20 readiness checks using `monitor-evavo.py`;
9. exits nonzero if readiness fails.

The Python controller is preferred for agent automation because it also records a managed PID and log location.

## Troubleshooting

### Service offline

```powershell
python evavo.py status
python evavo.py start
```

### Port 8188 conflict

```powershell
Get-NetTCPConnection -LocalPort 8188 -State Listen
Get-CimInstance Win32_Process -Filter "ProcessId=<PID>" | Select-Object ProcessId,CommandLine
```

Do not use `taskkill /IM python.exe` as a generic fix; it can terminate unrelated Python workloads.

### Wrapper failure

```powershell
python evavo-wrapper.py health_check "{}"
```

Wrapper stdout is exactly one JSON object. Nonzero exit status means the wrapper could not validate the service.

### Task history corruption or permissions

The tracker refuses to silently replace malformed history. If it reports `CORRUPT_HISTORY`, preserve the existing file, repair/restore it, or intentionally move it aside before continuing.

Choose an `EVAVO_TASK_HISTORY` location writable by the current Windows account when the repository itself is read-only.

### Batch partial failure

The table/JSON output includes per-task `error_code` and `message`. The command exits `1` if any requested item failed to queue, while successful items are still tracked.

## Validation

Run the standard-library integration suite:

```powershell
python evavo.py test
```

or:

```powershell
python test-operations.py
```

It validates:

- mock service startup and health;
- wrapper health contract;
- task ID generation;
- monitor health output;
- concurrent batch queueing and persistence;
- nonzero offline monitoring behavior.

## Security baseline

- Service binds to loopback only (`127.0.0.1`) by default.
- The mock server refuses non-loopback bind values.
- Request bodies are capped at 1 MiB.
- Prompts must be non-empty and are capped at 100,000 characters.
- Startup scripts do not indiscriminately terminate Python processes.

Loopback is not authentication. If the service is ever exposed beyond the local machine, add authentication/authorization and firewall rules before doing so.
