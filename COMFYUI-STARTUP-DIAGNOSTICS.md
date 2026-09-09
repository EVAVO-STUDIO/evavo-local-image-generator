# ComfyUI startup diagnostics

EVAVO treats ComfyUI startup as an observable lifecycle, not a blind subprocess timeout.

## Normal agent path

The shared Claude/ChatGPT MCP exposes:

```text
ensure_backend
diagnose_backend
last_startup_failure
repair_backend_dependencies
```

Preferred recovery sequence:

```text
last_startup_failure
diagnose_backend(seconds=60, cpu=true)
repair_backend_dependencies()  # only when category == missing_dependency
diagnose_backend(seconds=60, cpu=true)
ensure_backend
real generation proof
```

`diagnose_backend` runs a bounded owned-child diagnostic and returns structured failure evidence. `last_startup_failure` is read-only.

`repair_backend_dependencies` is deliberately narrower than a package manager:

- normal mutation requires current EVAVO-owned `missing_dependency` evidence;
- the exact ComfyUI workdir + Python recorded in structured startup evidence are used when available;
- otherwise EVAVO uses the canonical first discovered ComfyUI runtime;
- only that checkout's own `requirements.txt` is synchronized;
- no arbitrary package/module/Python/ComfyUI path/URL is accepted from MCP;
- no shell is used;
- a structured repair receipt identifies the selected workdir/interpreter;
- a `custom_node_dependency` does not authorize mutation of core ComfyUI requirements.

If the category is `custom_node_dependency`, isolate with:

```text
diagnose_backend(seconds=60, cpu=true, disable_all_custom_nodes=true)
```

and repair the reviewed custom node separately.

## Canonical updater self-recovery

The one-command Windows setup:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

now performs this sequence automatically:

1. authoritative full repository verification;
2. strict `agent-doctor --repair` plus optional runtime/model provisioning;
3. if strict doctor fails, **one** call to `recover-comfyui.py`;
4. `recover-comfyui.py` performs only normal evidence-gated dependency repair (`force_sync=False`);
5. strict doctor runs again and must prove native image-generation readiness;
6. only after that proof does setup continue to bootstrap and agent configuration.

Disable only the dependency-repair retry when troubleshooting:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIDependencyRepair
```

Runtime/model provisioning is controlled separately with `-SkipComfyUIProvision`.

The updater never enables forced dependency synchronization.

## Structured startup evidence

Startup failures are persisted at:

```text
<repo>\.evavo\native-comfyui-last-failure.json
```

The record can include the selected Python interpreter, `main.py`, working directory, full launch command, stable failure category, missing-module names, port ownership and a bounded log tail. Full process output remains in `.evavo\native-comfyui.log`.

The bounded diagnostic log lives at:

```text
<repo>\.evavo\comfy-startup-output.txt
```

The repair bridge chooses the newest EVAVO-owned structured/log evidence before deciding whether normal dependency mutation is admissible.

## Source and Windows-portable runtime targeting

EVAVO handles source installs and common Windows portable layouts. A portable layout such as:

```text
C:\AI\ComfyUI_windows_portable\
  ComfyUI\main.py
  ComfyUI\requirements.txt
  python_embeded\python.exe
```

is repaired using the `ComfyUI` workdir and its parent embedded Python. Source installs prefer their `.venv` / `venv` interpreter.

The standalone repair command now searches the same practical locations used by runtime discovery, including sibling repos, `C:\Gitrepos`, `C:\GitRepos`, `C:\AI`, common user locations, portable roots and `EVAVO_COMFYUI_SEARCH_PATHS`.

## Dependency repair

For a proven core missing dependency, prefer MCP:

```text
repair_backend_dependencies()
```

When MCP is unavailable, direct CLI repair can use automatic discovery:

```powershell
python .\repair-comfyui-dependencies.py
```

or an explicit operator-selected runtime:

```powershell
python .\repair-comfyui-dependencies.py `
  --comfy-home C:\Gitrepos\ComfyUI `
  --python C:\Gitrepos\ComfyUI\.venv\Scripts\python.exe
```

The standalone command:

- verifies `main.py` + `requirements.txt`;
- selects the matching source/portable interpreter;
- probes the target import;
- runs only that interpreter's `pip install -r <selected ComfyUI>\requirements.txt` when needed;
- does not add `--upgrade` implicitly;
- runs `pip check` and re-imports the target module;
- persists a bounded receipt under the selected ComfyUI `.evavo` directory;
- never starts/stops/kills Python or ComfyUI processes.

## Forced requirements synchronization

Forced synchronization is **not normal model authority**.

For MCP, `force_sync=true` is accepted only when the workstation owner has explicitly configured:

```text
EVAVO_ALLOW_FORCED_DEPENDENCY_REPAIR=1
```

Without that setting the tool returns `FORCE_SYNC_NOT_AUTHORIZED` before reading repair evidence or launching a subprocess.

The canonical updater does **not** set this variable.

A direct operator CLI can still deliberately run:

```powershell
python .\repair-comfyui-dependencies.py --force-sync
```

Direct CLI use is an explicit workstation/operator action, not automatic ChatGPT/Claude authority.

After any repair, re-run diagnostics/readiness and then a real image generation. Package installation alone is not proof of a healthy renderer.

## Bounded CLI diagnostic

When MCP is unavailable:

```powershell
python .\diagnose-comfyui-startup.py
```

The default probe runs for 60 seconds, launches only its owned child, captures stdout/stderr, probes `/system_stats`, and terminates only the process tree it created. It never kills a pre-existing listener on 8188.

Custom-node isolation:

```powershell
python .\diagnose-comfyui-startup.py --disable-all-custom-nodes
```

## Stable failure categories

- `port_in_use`: another process owns the endpoint or bind fails.
- `custom_node_dependency`: missing Python dependency associated with a custom node/prestartup path.
- `missing_dependency`: core Python import failure without a custom-node signal.
- `torch_or_cuda_initialization`: PyTorch/CUDA initialization failure.
- `startup_exception`: another traceback/fatal exception before HTTP readiness.
- `process_exited`: child exits before readiness without a more specific category.
- `startup_timeout`: child remains alive but `/system_stats` never becomes ready.
- `ready`: diagnostic child becomes HTTP-ready.

## Process safety

Never use broad cleanup such as:

```text
taskkill /IM python.exe /F
Stop-Process -Name python
```

Lifecycle actions must target a known owned PID/process tree or verify exact expected process identity. User-managed ComfyUI is never killed by EVAVO.

Windows lifecycle locking uses named mutexes, while migration logic still honors older advisory lock files safely.
