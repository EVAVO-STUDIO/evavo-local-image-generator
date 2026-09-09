# ComfyUI startup diagnostics

EVAVO treats ComfyUI startup as an observable lifecycle, not a blind subprocess timeout.

## Normal agent path

The image-generator MCP exposes:

```text
ensure_backend
diagnose_backend
last_startup_failure
repair_backend_dependencies
```

For Claude, ChatGPT or another connected MCP agent, prefer the shared MCP lifecycle before dropping to shell automation:

```text
last_startup_failure
diagnose_backend(seconds=60, cpu=true)
repair_backend_dependencies()  # only when category == missing_dependency
diagnose_backend(seconds=60, cpu=true)
ensure_backend
real generation proof
```

`diagnose_backend` runs the same bounded owned-child diagnostic and returns structured failure evidence without exposing arbitrary shell authority. `last_startup_failure` is read-only and returns the most recently persisted startup failure.

`repair_backend_dependencies` is the preferred agent repair surface. It does not accept arbitrary package names, Python paths or ComfyUI paths from MCP callers. Normal mutation is admitted only when the last structured startup failure is a core `missing_dependency`. It invokes the repository's bounded repair command without a shell, synchronizes only the discovered checkout's own `requirements.txt` into its selected ComfyUI Python, and returns a structured receipt.

If the category is `custom_node_dependency`, the shared repair tool refuses to mutate core ComfyUI requirements. Isolate with `diagnose_backend(seconds=60, cpu=true, disable_all_custom_nodes=true)` and repair the reviewed custom node separately.

Startup failures preserve a structured record at:

`<evavo-local-image-generator>/.evavo/native-comfyui-last-failure.json`

The record includes the selected Python interpreter, `main.py`, working directory, full launch command, stable failure category, missing-module names, port ownership when available, and a bounded log tail. The full process output remains in `.evavo/native-comfyui.log`.

On Windows, direct checkouts such as `C:\AI\ComfyUI\main.py` detect a parent-level portable interpreter such as `C:\AI\python_embeded\python.exe`. This avoids accidentally launching ComfyUI with an unrelated system Python that does not have ComfyUI's dependencies.

When the selected interpreter is the Windows portable embedded Python, EVAVO matches ComfyUI's portable launch isolation:

```text
C:\AI\python_embeded\python.exe -s C:\AI\ComfyUI\main.py --windows-standalone-build ...
```

Source/venv installs do not receive portable-only flags.

## Dependency repair

When the diagnostic category is `missing_dependency`, do not guess a PyPI version and do not install the package into a global/system Python. Prefer MCP:

```text
repair_backend_dependencies()
```

The MCP repair bridge derives the target import from the last structured `missing_dependency` failure, then invokes the bounded repository repair command. It is intentionally narrower than a package manager and never exposes arbitrary package installation authority to Claude or ChatGPT.

When MCP is unavailable, the CLI fallback uses the same local checkout authority:

```powershell
python .\repair-comfyui-dependencies.py --comfy-home C:\AI\ComfyUI
```

The repair command:

- selects the same local/embedded Python layout used by ComfyUI;
- probes `comfy_aimdo` by default, or another explicitly supplied diagnostic module;
- runs that interpreter's `pip install -r <ComfyUI>\requirements.txt` only when repair is required;
- never adds `--upgrade` implicitly;
- runs `pip check` and re-imports the target module afterwards;
- persists the bounded result to `<ComfyUI>\.evavo\dependency-repair-last.json`;
- never starts, stops, or kills Python/ComfyUI processes.

For another missing core module reported by diagnostics, CLI fallback may use:

```powershell
python .\repair-comfyui-dependencies.py --comfy-home C:\AI\ComfyUI --module <reported_module>
```

If the failure indicates that the environment as a whole is incomplete rather than one target import, an authorised operator may deliberately request a full checkout requirements sync:

```text
repair_backend_dependencies(force_sync=true)
```

or, without MCP:

```powershell
python .\repair-comfyui-dependencies.py --comfy-home C:\AI\ComfyUI --force-sync
```

`force_sync` is an explicit override, not the normal path.

After a successful dependency repair, agents must re-run `diagnose_backend(seconds=60, cpu=true)`, then `ensure_backend`, then an actual generation smoke test. Package installation alone is not proof that the service is healthy.

Agents with EVAVO Workstation Bridge/Operator execution authority should perform needed fallback repair themselves and wait for the terminal receipt. They should not hand routine PowerShell/Python execution back to the user merely because the operation is on Windows.

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

## Process and lock safety for agents

Do not use broad cleanup such as `taskkill /IM python.exe /F`, `Stop-Process -Name python`, or equivalent catch-all termination. Those commands can kill unrelated development, automation, model, or application processes. Lifecycle actions must target a known owned PID/process tree or verify the process identity and expected ComfyUI command line before termination.

Windows lifecycle locks use named mutexes rather than creating new persistent `.lock` files. During migration, an existing legacy lock file is still honored before it is removed after release. This keeps mutual exclusion intact while avoiding stale lock-file artifacts that external agents may misinterpret as an active blocker.
