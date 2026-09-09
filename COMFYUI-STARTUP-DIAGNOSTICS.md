# ComfyUI startup diagnostics

EVAVO treats ComfyUI startup as an observable lifecycle, not a blind subprocess timeout.

## Normal agent path

The image-generator MCP already exposes `ensure_backend`. Startup failures now preserve a structured record at:

`<evavo-local-image-generator>/.evavo/native-comfyui-last-failure.json`

The record includes the selected Python interpreter, `main.py`, working directory, full launch command, stable failure category, missing-module names, port ownership when available, and a bounded log tail. The full process output remains in `.evavo/native-comfyui.log`.

On Windows, direct checkouts such as `C:\AI\ComfyUI\main.py` now detect a parent-level portable interpreter such as `C:\AI\python_embeded\python.exe`. This avoids accidentally launching ComfyUI with an unrelated system Python that does not have ComfyUI's dependencies.

## Bounded 60-second probe

From this repository:

```powershell
python .\diagnose-comfyui-startup.py
```

The default probe runs for 60 seconds, launches ComfyUI in CPU mode, captures stdout and stderr separately in real time, probes `/system_stats`, and terminates only the process tree it created. It never kills a pre-existing listener on port 8188.

If the result recommends custom-node isolation, run:

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
