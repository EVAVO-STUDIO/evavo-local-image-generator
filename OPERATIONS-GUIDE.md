# EVAVO Local Image Generator - Operations Guide

This guide describes the repository's actual local operational control plane. The supported runtime is **Python 3.10+**. The operations layer uses only the Python standard library; `requirements.txt` is for the wider generator/tooling repository.

## Preferred workflow

For normal use, one command performs the operational bootstrap:

```powershell
python evavo.py bootstrap
```

That sequence:

1. requires branch `main`;
2. refuses to overwrite local changes;
3. runs `git pull --ff-only origin main`;
4. runs the environment doctor;
5. runs the integration test suite;
6. starts the managed local service;
7. verifies final service status.

If the checkout is old enough that `evavo.py` does not exist yet, fast-forward once:

```powershell
git pull --ff-only origin main
python evavo.py bootstrap --skip-pull
```

Windows operators can instead run:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

## Core commands

```powershell
python evavo.py doctor
python evavo.py sync
python evavo.py bootstrap
python evavo.py start
python evavo.py status
python evavo.py generate --prompts "sunset landscape" "cyberpunk city" --project demo
python evavo.py tasks --limit 20
python evavo.py stats
python evavo.py test
python evavo.py stop
```

`START-EVAVO-SERVICES.bat` remains available, but it is intentionally thin: it finds Python, runs `evavo.py doctor`, delegates startup to `evavo.py start`, then displays `evavo.py status`. Process lifecycle logic lives in Python rather than being duplicated in batch syntax.

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

Generation results -------------> task_history.json
                                  atomic + lock protected
```

The current mock server is a deterministic local queue/API surface for operational validation. It does **not** render images. The real ComfyUI adapter should preserve the same service identity, health and queue response contract so the wrapper/monitor/batch/controller layers do not need to change.

## Environment doctor

Run:

```powershell
python evavo.py doctor
```

Machine-readable form:

```powershell
python evavo.py doctor --json
```

The doctor checks:

- Python 3.10+ and interpreter path;
- presence of all required operational files;
- whether `asyncio` resolves from the standard library instead of `site-packages`;
- valid loopback endpoint syntax;
- Git repository presence;
- branch `main`;
- local/upstream commit state when an upstream is configured;
- local worktree cleanliness;
- current service health.

Python already includes `asyncio`. Do **not** install the PyPI `asyncio` package for this repository. If it shadows the standard library, doctor reports it.

## Start and stop

Default service:

```powershell
python evavo.py start
python evavo.py status
python evavo.py stop
```

The managed mock server defaults to:

```text
http://127.0.0.1:8188
```

For isolated testing, other loopback ports are supported:

```powershell
python evavo.py start --endpoint http://127.0.0.1:18190
python evavo.py status --endpoint http://127.0.0.1:18190
python evavo.py stop
```

Only `http://127.0.0.1:<port>` and `http://localhost:<port>` managed endpoints are accepted. Paths, credentials, query strings and non-loopback hosts are rejected.

Managed service state and logs are stored under:

```text
.evavo/operations-service.json
.evavo/mock-service.log
```

If startup fails or times out, the controller terminates the process it started and clears stale managed state before returning an error.

## Health contract

A healthy service must:

- return HTTP 2xx;
- return valid JSON;
- identify as `evavo-local-image-generator`;
- report protocol version `1`;
- report `ready` or `ok`.

Example:

```json
{
  "service": "evavo-local-image-generator",
  "protocol_version": 1,
  "status": "ready",
  "mode": "mock"
}
```

Monitoring commands:

```powershell
python monitor-evavo.py
python monitor-evavo.py --json
python monitor-evavo.py --continuous --interval 10
python monitor-evavo.py --continuous --interval 10 --json
```

The one-shot monitor exits nonzero when degraded/offline, so automation can trust its process exit status.

## Queue generation

Preferred:

```powershell
python evavo.py generate --prompts "landscape" "portrait" "abstract" --project production_batch
```

Direct batch usage:

```powershell
python generate-batch.py --examples
python generate-batch.py --prompts "prompt one" "prompt two" --concurrency 4 --json
```

`generate-batch.py`:

- performs service identity/readiness preflight by default;
- uses `asyncio.create_subprocess_exec` rather than blocking `subprocess.run`;
- bounds concurrency (`1..64`, default `4`);
- enforces per-wrapper timeout;
- validates wrapper JSON and returned task IDs;
- records successes and failures to task history;
- exits `1` on partial batch failure;
- exits `3` when preflight fails.

## Task history

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
python task-tracker.py clear --yes
```

History defaults to:

```text
<repository>\task_history.json
```

Override with:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\task_history.json"
```

Persistence uses an inter-process lock, temporary-file write, flush/fsync and atomic `os.replace()` to avoid lost updates and truncated JSON. Corrupt JSON is reported explicitly rather than silently replaced.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `COMFYUI_ENDPOINT` | `http://127.0.0.1:8188` | Service base URL |
| `EVAVO_TASK_HISTORY` | `<repo>/task_history.json` | Persistent task history location |
| `EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE` | `bee://primary/EVAVO/ImageGeneration` | Logical storage root used by package tooling |

## `bee://` storage

`bee://` values are logical resource URIs, not Windows filesystem paths. Resolve them through the storage layer rather than concatenating them with Windows paths. Path/URI translation should remain centralized and traversal outside configured roots should be rejected.

## Validation

Run:

```powershell
python evavo.py test
```

The integration suite validates:

- mock service startup and readiness;
- wrapper health contract;
- queue submission and `evavo_*` task IDs;
- monitor operational JSON;
- concurrent two-prompt batching;
- batch-to-history persistence;
- nonzero offline monitor behavior;
- doctor handling of an isolated loopback endpoint;
- controller `start -> status -> stop` lifecycle on an isolated test port;
- managed state cleanup after stop.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Requested operation succeeded |
| `1` | General or partial operation failure |
| `2` | Invalid CLI/configuration/prerequisite |
| `3` | Service/wrapper unavailable, degraded, startup timeout or sync timeout |
| `4` | Task not found (tracker update) |

## Troubleshooting

### Old checkout still running old scripts

Symptoms include the old monitor JSON fields (`comfyui`, `evavo_wrapper`, `overall`) or a batch table that reports `error / N/A` without preflight information.

Fix:

```powershell
git pull --ff-only origin main
python evavo.py bootstrap --skip-pull
```

### Service offline

```powershell
python evavo.py doctor
python evavo.py start
python evavo.py status
```

### Startup failure

```powershell
Get-Content .\.evavo\mock-service.log -Tail 100
Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue
```

Do not use `taskkill /IM python.exe` as a generic fix. It can terminate unrelated Python workloads.

### Wrapper failure

```powershell
python evavo-wrapper.py health_check "{}"
```

Wrapper stdout is exactly one JSON object. Nonzero exit status means the wrapper could not validate the service.

### Task history corruption or permissions

If the tracker reports `CORRUPT_HISTORY`, preserve the existing file and repair/restore it or intentionally move it aside. Choose an `EVAVO_TASK_HISTORY` location writable by the current Windows account when the repository is read-only.

## Repository hygiene

Git metadata backup directories such as `.git.backup`, `.git.broken`, `.git.final-backup`, `.git.framework-backup`, `.git.new`, `.git.old.backup` and `.git.test-backup` are not part of the product and are removed/ignored. Do not commit copied `.git*` metadata into this repository.

## Security baseline

- Managed mock service is loopback-only.
- Non-loopback binds are rejected.
- Request bodies are capped at 1 MiB.
- Prompts must be non-empty and are capped at 100,000 characters.
- Wrapper output is a stable JSON object for automation.
- Startup/stop tooling does not indiscriminately terminate Python processes.
- Bootstrap uses `git pull --ff-only` and refuses to overwrite a dirty worktree.

Loopback is not authentication. Before exposing a real backend beyond the local machine, add authentication/authorization, firewall restrictions, payload validation and secret-safe logging.
