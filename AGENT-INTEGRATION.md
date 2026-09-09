# EVAVO Agent Integration

EVAVO exposes one native ComfyUI generation pipeline to Claude, ChatGPT-compatible MCP clients, Codex/IDE agents, direct Python automation and the `evavo.py` CLI.

## Canonical Windows setup

From a current checkout, the preferred setup is one command:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

By default it:

1. safely fast-forwards `main`;
2. installs/upgrades repository dependencies including `mcp[cli]>=2,<3`;
3. runs offline ComfyUI provisioning safety tests;
4. runs operational integration tests;
5. runs negotiated MCP stdio + Streamable HTTP generation/history tests;
6. bootstraps/selects the generation backend;
7. installs/updates Claude Desktop stdio MCP configuration while preserving other servers;
8. installs the current-user HTTP MCP login autostart;
9. starts the HTTP MCP listener if it is not already running;
10. runs `agent-doctor.py --repair --provision` as a strict real-generation readiness gate;
11. provisions official ComfyUI when no installation exists;
12. provisions an explicitly configured checkpoint source when required;
13. verifies final backend status.

Use `-SkipAgentConfiguration` only when intentionally troubleshooting without changing local agent configuration. Use `-SkipComfyUIProvision` when the workstation must not install/update ComfyUI automatically.

## Automation contract

An agent does **not** need to know how ComfyUI was installed or manually start it first.

On a generation call EVAVO can:

1. check the configured endpoint for a real native ComfyUI;
2. reject the deterministic EVAVO mock as a renderer;
3. discover a local source or Windows portable ComfyUI install;
4. safely provision the official ComfyUI source runtime when enabled and no install exists;
5. reuse portable installs without modifying their embedded Python runtime;
6. stop only an EVAVO-owned mock if it is occupying port 8188;
7. start native ComfyUI in the background when installed but offline;
8. wait for `/system_stats` readiness;
9. discover checkpoints through `CheckpointLoaderSimple`;
10. queue `/prompt` with the built-in or a custom API workflow;
11. poll `/history/<prompt_id>`;
12. download `/view` outputs atomically;
13. persist queue/completion/failure state plus backend/checkpoint/output metadata in the shared EVAVO task history;
14. return concrete local file paths to the calling agent.

## ComfyUI discovery

Automatic discovery covers common Windows locations, sibling Git repositories, source virtual environments and portable installs, including paths such as:

```text
C:\ComfyUI
C:\Gitrepos\ComfyUI
C:\GitRepos\ComfyUI
C:\AI\ComfyUI
C:\ComfyUI_windows_portable
%USERPROFILE%\ComfyUI
%USERPROFILE%\Documents\ComfyUI
%USERPROFILE%\Downloads\ComfyUI_windows_portable
%USERPROFILE%\Desktop\ComfyUI
```

For a non-standard installation:

```powershell
$env:EVAVO_COMFYUI_HOME = "D:\AI\ComfyUI"
```

To force the exact Python interpreter used to launch a source checkout:

```powershell
$env:EVAVO_COMFYUI_PYTHON = "D:\AI\ComfyUI\.venv\Scripts\python.exe"
```

Additional roots can be supplied through `EVAVO_COMFYUI_SEARCH_PATHS` using the platform path separator.

## Runtime provisioning

Provision the official ComfyUI source runtime explicitly:

```powershell
python provision-comfyui.py
```

The provisioner:

- reuses an existing standard source/portable install when found;
- clones `https://github.com/Comfy-Org/ComfyUI.git` only when no install exists;
- never overwrites a non-ComfyUI target;
- never updates a dirty source checkout;
- creates an isolated `.venv` for source installs;
- detects NVIDIA and follows ComfyUI's documented stable CUDA PyTorch installation path;
- installs ComfyUI's own `requirements.txt`;
- verifies Torch/CUDA/device visibility;
- records provisioning state in `.evavo/comfyui-provision.json`;
- does not silently select or license a diffusion model.

Agents can call the parameterless MCP tool:

```text
provision_backend
```

That tool intentionally accepts **no repository URL or model URL arguments**. It can only use the fixed EVAVO provisioner and model sources configured by the workstation owner.

Local agent profiles set:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
```

so `ensure_backend`, `health_check`, `generate_image` and `generate_batch` may provision a missing runtime before starting it.

## Checkpoint provisioning

A real checkpoint remains a blocking requirement for real generation. EVAVO will not guess or silently choose one.

Preferred local-file setup:

```powershell
$env:EVAVO_CHECKPOINT_FILE = "D:\AI\Models\your-model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<optional expected sha256>"
$env:EVAVO_CHECKPOINT_NAME = "your-model.safetensors"
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Explicit HTTPS source when appropriate:

```powershell
$env:EVAVO_CHECKPOINT_URL = "https://example.com/your-model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<strongly recommended expected sha256>"
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The provisioner supports:

```text
EVAVO_CHECKPOINT_FILE
EVAVO_CHECKPOINT_URL
EVAVO_CHECKPOINT_SHA256
EVAVO_CHECKPOINT_NAME
```

Safety behavior:

- HTTPS is required for URL downloads unless `--allow-http-checkpoint` is explicitly passed to the provisioner;
- model filenames are reduced to simple safe filenames and traversal is rejected;
- downloads stream through `.part` files and only become final after verification;
- URL downloads are capped at 32 GiB;
- SHA-256 can be required and is verified before final placement;
- an existing different destination file is never overwritten;
- source and Windows-portable `models/checkpoints` layouts are both supported;
- Claude/HTTP installers intentionally do **not** persist `EVAVO_CHECKPOINT_URL` because signed URLs may contain secrets/tokens.

To provision only a configured model into an existing source/portable install:

```powershell
python provision-comfyui.py --target "D:\AI\ComfyUI" --checkpoint-only
```

## Claude: stdio MCP

The workstation updater installs this automatically. It can also be installed independently:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

The installer:

- runs MCP integration tests first;
- resolves the actual Python executable;
- uses the absolute repository path through `PYTHONPATH`;
- backs up an existing `claude_desktop_config.json`;
- preserves existing MCP servers;
- adds/updates only `evavo-local-image-generator`;
- enables safe ComfyUI auto-provisioning;
- persists local/non-secret ComfyUI/model settings;
- deliberately does not persist potentially secret checkpoint URLs.

Restart Claude Desktop after installation so it reloads its MCP configuration.

Underlying server command:

```text
python -m evavo_local_image_generator.mcp_server --transport stdio
```

## ChatGPT/local MCP clients: Streamable HTTP

Manual foreground start:

```powershell
.\START-AGENT-MCP.ps1
```

Install current-user Windows login autostart and start it now:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

The autostart installer embeds only safe local settings needed after reboot. Signed checkpoint URLs are not written into the Startup command.

The HTTP transport is restricted to loopback and uses exact host/origin allowlists for the configured port with DNS-rebinding protection enabled.

A cloud-hosted client cannot directly reach workstation `127.0.0.1` unless the product provides a local bridge/connector. Do not expose this listener or ComfyUI directly to the public internet just to make it reachable.

## Agent tools

The MCP server exposes:

- `provision_backend` — constrained official-runtime/model provisioning using workstation configuration only;
- `ensure_backend` — verify, auto-provision when enabled, and auto-start native ComfyUI;
- `health_check` — backend version/device health;
- `discover_backends` — local ComfyUI installations EVAVO can launch;
- `list_checkpoints` — installed checkpoints;
- `generate_image` — one image, queue or wait/download, persisted to shared history;
- `generate_batch` — bounded-concurrency multi-prompt generation, also persisted;
- `generation_status` — inspect a prompt ID and reconcile history;
- `collect_generation` — wait/download an existing prompt and reconcile history;
- `task_history` — recent shared CLI + MCP generation history;
- `task_statistics` — shared task counts by status;
- `stop_managed_backend` — stop only native ComfyUI started by EVAVO.

`generate_image` and `generate_batch` default to `auto_start=true` and `wait=true` for one-call agent workflows.

## Shared task history

MCP and CLI generation use the same lock-protected, atomic history file:

```text
task_history.json
```

New records preserve:

```text
task_id
prompt
project_name
status
backend_mode
checkpoint
workflow_path
output_dir
output_uris[]
errors/timestamps
```

Older minimal history files remain readable.

Override history location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\image-generation-history.json"
```

This allows a Claude-generated task to be inspected later from `evavo.py tasks`, and a CLI-generated task to appear through the MCP `task_history` tool.

## Default generated files

Agent downloads default to:

```text
<repo>\.evavo\outputs\<project>\
```

Override globally:

```powershell
$env:EVAVO_GENERATION_OUTPUT_DIR = "D:\EVAVO\generated"
```

or pass `output_dir` to a generation tool.

## Custom ComfyUI API workflow

For Flux, SDXL variants, custom nodes, ControlNet or other pipelines export API-format JSON from ComfyUI and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\workflows\production-api.json"
```

Supported placeholders inside string values:

```text
{{PROMPT}}
{{NEGATIVE_PROMPT}}
{{WIDTH}}
{{HEIGHT}}
{{STEPS}}
{{CFG}}
{{SEED}}
{{CHECKPOINT}}
{{FILENAME_PREFIX}}
```

A tool call can also pass `workflow_path` explicitly.

## Agent doctor

Read-only diagnosis:

```powershell
python agent-doctor.py
```

Strict repair/readiness gate with provisioning:

```powershell
python agent-doctor.py --repair --provision
```

Native ComfyUI and at least one usable checkpoint are required. The command fails rather than reporting success on the deterministic mock fallback. If no model source was configured, a missing checkpoint remains an explicit failure with instructions to configure one.

Machine-readable status:

```powershell
python agent-doctor.py --repair --provision --json
```

## Validation

The full workstation updater runs:

```powershell
python test-provisioning.py
python test-agent-integration.py
python evavo.py test
```

Provisioning tests are offline and verify traversal rejection, local checkpoint copy/hash verification, idempotency, destination-conflict safety, HTTPS enforcement and source/portable layouts.

Agent tests verify:

- MCP v2 in-process negotiation/tool discovery;
- real stdio client/server negotiation;
- real Streamable HTTP client/server negotiation;
- exact advertised tool inventory including parameterless `provision_backend`;
- ComfyUI discovery;
- rejection of the EVAVO mock as native;
- HTTP MCP `generate_image` end-to-end output download;
- HTTP MCP `generate_batch` end-to-end multi-image generation;
- rich shared task-history persistence and task statistics.

Operational tests separately verify mock/native health, native workflow submission, output history and file downloads, rich batch tracking, legacy-history compatibility, offline behavior and controller lifecycle.

## Safety/lifecycle rules

- Native and MCP HTTP listeners are loopback by default.
- EVAVO never uses broad `taskkill /IM python.exe` cleanup.
- `stop_managed_backend` stops only a PID recorded as started by EVAVO.
- An already-running user-managed ComfyUI is reused and is not stopped by EVAVO.
- Existing standard source/portable installs are reused before creating a new sibling checkout.
- Portable embedded Python is not modified by the provisioner.
- If an EVAVO-managed mock is occupying port 8188 and a native install is available, EVAVO may stop only that recorded mock PID before starting native ComfyUI.
- Output downloads use temporary files followed by atomic replacement.
- Legacy launchers are compatibility shims and no longer spawn persistent `cmd /k`, `-NoExit`, Ollama/Kokoro, or surprise multimodal jobs.
