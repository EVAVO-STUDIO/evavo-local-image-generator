# ComfyUI startup diagnostics

EVAVO treats ComfyUI startup as an observable lifecycle, not a blind subprocess timeout.

## Normal agent path

The image-generator MCP exposes:

```text
ensure_backend
diagnose_backend
last_startup_failure
```

For Claude, ChatGPT or another connected MCP agent, prefer `diagnose_backend(seconds=60, cpu=true)` before dropping to shell automation. The tool runs the same bounded owned-child diagnostic and returns structured failure evidence without exposing arbitrary shell authority. `last_startup_failure` is read-only and returns the most recently persisted startup failure.

Startup failures preserve a structured record at:

`<evavo-local-image-generator>/.evavo/native-comfyui-last-failure.json`

The record includes the selected Python interpreter, `main.py`, working directory, full launch command, stable failure category, missing-module names, port ownership when available, and a bounded log tail. The full process output remains in `.evavo/native-comfyui.log`.

On Windows, direct checkouts such as `C:\AI\ComfyUI\main.py` detect a parent-level portable interpreter such as `C:\AI\python_embeded\python.exe`. This avoids accidentally launching ComfyUI with an unrelated system Python that does not have ComfyUI's dependencies.

When the selected interpreter is the Windows portable embedded Python, EVAVO matches ComfyUI's portable launch isolation:

```text
C:\AI\python_embeded\python.exe -s C:\AI\ComfyUI\main.py --windows-standalone-build ...
```

Source/venv installs do not receive portable-only flags.

## Bounded 60-second CLI probe

When MCP is unavailable or the client has not yet reloaded the updated server, run from this repository:

```powershell
python .\diagnose-comfyui-startup.py
```

The default probe runs for 60 seconds, launches ComfyUI in CPU mode, captures stdout and stderr separately in real time, probes `/system_stats`, and terminates only the process tree it created. It never kills a pre-existing listener on port 8188.

If the result recommends custom-node isolation, use MCP `diagnose_backend(seconds=60, cpu=true, disable_all_custom_nodes=true)` or run:

```powershell
python .\diagnose-comfyui-startup.py --disable-all-custom-nodes
```

If that second probe becomes healthy, the failure is in custom-node startup rather than core ComfyUI.

## Stable failure categories

- `port_in_use`: another process already owns the endpoint or ComfyUI reports an address-bind conflict.
- `custom_node_dependency`: a missing Python module appears alongside custom-node/prestartup output.
- `missing_dependency`: core Python import failure without a custom-node signal.
- `torch_or_cuda_initialization`: PyTorch/CUDA initialization failure.
- `startup_exception`: another traceback/fatal exception before HTTP readiness.
- `process_exited`: the child exits before readiness without a more specific signature.
- `startup_timeout`: the child stays alive but `/system_stats` never becomes ready by the deadline.
- `ready`: the diagnostic child becomes HTTP-ready.

## Lock behavior for agents

Windows lifecycle locks use named mutexes rather than creating new persistent `.lock` files. During migration, an existing legacy lock file is still honored before it is removed after release. This keeps mutual exclusion intact while avoiding stale lock-file artifacts that external agents may misinterpret as an active blocker.
