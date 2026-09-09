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
3. runs offline ComfyUI provisioning/runtime-safety tests;
4. runs operational integration tests;
5. runs negotiated MCP stdio + Streamable HTTP generation/history/image-content tests;
6. bootstraps/selects the generation backend;
7. installs/updates Claude Desktop stdio MCP configuration while preserving other servers;
8. installs the current-user HTTP MCP login autostart;
9. starts the HTTP MCP listener if it is not already running;
10. runs `agent-doctor.py --repair --provision` as a strict real-generation readiness gate;
11. provisions official ComfyUI when no installation exists;
12. provisions an explicitly configured checkpoint source when required;
13. validates shared model roots and the available ComfyUI model inventory;
14. verifies final backend status.

Use `-SkipAgentConfiguration` only when intentionally troubleshooting without changing local agent configuration. Use `-SkipComfyUIProvision` when the workstation must not install/update ComfyUI automatically.

## Automation contract

An agent does **not** need to know how ComfyUI was installed or manually start it first.

On a normal generation call EVAVO can:

1. check the configured endpoint for a real native ComfyUI;
2. reject the deterministic EVAVO mock as a renderer;
3. discover a local source or Windows portable ComfyUI install;
4. safely provision the fixed official ComfyUI source runtime when enabled and no install exists;
5. reuse portable installs without modifying their embedded Python runtime;
6. stop only an identity-verified EVAVO-owned mock if it occupies port 8188;
7. start native ComfyUI in the background when installed but offline;
8. inject EVAVO-managed shared model roots without rewriting ComfyUI's own config;
9. restart only an identity-verified EVAVO-managed ComfyUI when that effective shared-model config changes;
10. wait for `/system_stats` readiness;
11. inspect available model-loader inventories;
12. auto-provision an owner-configured checkpoint when the built-in workflow needs one;
13. queue `/prompt` with the built-in or a custom API workflow;
14. poll `/history/<prompt_id>`;
15. download `/view` outputs atomically;
16. persist queue/completion/failure state plus backend/checkpoint/workflow/output metadata in shared task history;
17. return concrete local file paths;
18. optionally return the generated image itself as native MCP image content through `read_output_image`.

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
- reuses a healthy existing source runtime after a Torch/CUDA probe and `main.py --help` smoke check instead of reinstalling dependencies;
- repairs/reinstalls source dependencies only when that runtime probe fails;
- detects NVIDIA and follows ComfyUI's documented stable CUDA PyTorch installation path;
- installs ComfyUI's own `requirements.txt` when required;
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
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

The checkpoint flag still does nothing unless `EVAVO_CHECKPOINT_FILE` or `EVAVO_CHECKPOINT_URL` was explicitly configured by the workstation owner.

## Checkpoint provisioning

A real checkpoint remains a blocking requirement for the built-in txt2img workflow. EVAVO will not guess or silently choose a model source.

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

Safety behavior:

- HTTPS is required unless `--allow-http-checkpoint` is explicitly passed to the standalone provisioner;
- filenames are reduced to simple safe names and traversal is rejected;
- downloads stream through `.part` files and only become final after verification;
- URL downloads are capped at 32 GiB;
- SHA-256 can be required and is verified before final placement;
- an existing different destination is never overwritten;
- source and Windows-portable `models/checkpoints` layouts are supported;
- Claude/HTTP installers intentionally do **not** persist `EVAVO_CHECKPOINT_URL` because signed URLs may contain secrets/tokens;
- custom API workflows do not trigger checkpoint provisioning merely because `CheckpointLoaderSimple` is empty.

Checkpoint-only repair:

```powershell
python provision-comfyui.py --target "D:\AI\ComfyUI" --checkpoint-only
```

## Shared model libraries

To reuse an existing model library instead of copying large files, set one or more local/network roots:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

`EVAVO_COMFYUI_MODEL_ROOTS` is accepted as an alias. Multiple roots use the operating system path separator (`;` on Windows).

EVAVO inspects only configured roots and maps directories that actually exist, including common locations for:

```text
checkpoints
loras / Lora / LyCORIS
vae / VAE
text_encoders / clip
diffusion_models / unet
clip_vision
controlnet / ControlNet / t2i_adapter
embeddings
upscale_models / ESRGAN / RealESRGAN / SwinIR
custom_nodes
and other ComfyUI model categories
```

EVAVO writes its own generated config:

```text
.evavo\extra-model-paths.yaml
```

and launches managed ComfyUI with:

```text
--extra-model-paths-config <repo>\.evavo\extra-model-paths.yaml
```

It does **not** edit or replace ComfyUI's own `extra_model_paths.yaml`.

The effective generated YAML is SHA-256 fingerprinted in managed runtime state. If the configured roots/layout change while an EVAVO-managed ComfyUI is running, EVAVO verifies the recorded process identity and restarts only that managed process so the new paths are actually loaded. A user-managed ComfyUI is never killed; in that case EVAVO reports that it cannot verify whether the requested shared roots were loaded.

Claude Desktop and Windows HTTP-login installers persist these shared-root settings so they survive restarts.

## Model inventory

Agents can inspect the models ComfyUI actually exposes through loader nodes before choosing a workflow:

```text
model_inventory
```

Current inventory categories include:

```text
checkpoints
loras
vae
controlnet
diffusion_models
text_encoders
clip_vision
upscale_models
```

Each category is queried independently. A missing optional loader node is reported for that category without making checkpoint generation fail. `agent-doctor.py` also summarizes these counts during readiness checks.

## Claude: stdio MCP

The workstation updater installs this automatically. It can also be installed independently:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

The installer resolves the actual Python/repository paths, runs MCP integration tests, backs up the existing Claude config, preserves other MCP servers, enables constrained ComfyUI/checkpoint repair, and persists local non-secret model/workflow/shared-root settings. Potentially secret checkpoint URLs are not persisted.

Restart Claude Desktop after installation so it reloads its MCP configuration.

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

The autostart installer embeds only safe local settings needed after reboot. Signed checkpoint URLs are not written into the Startup command. The HTTP transport is loopback-only and uses exact host/origin allowlists for the configured port with DNS-rebinding protection enabled.

A cloud-hosted client cannot directly reach workstation `127.0.0.1` unless the product provides a local bridge/connector. Do not expose this listener or ComfyUI directly to the public internet just to make it reachable.

## Agent tools

The MCP server exposes:

- `provision_backend` — constrained official-runtime/model provisioning using workstation configuration only;
- `ensure_backend` — verify, auto-provision when enabled, and auto-start native ComfyUI;
- `health_check` — backend version/device health;
- `discover_backends` — local ComfyUI installations EVAVO can launch;
- `list_checkpoints` — installed checkpoints;
- `model_inventory` — common ComfyUI loader-node model inventories;
- `generate_image` — one image, queue or wait/download, persisted to shared history;
- `generate_batch` — bounded-concurrency multi-prompt generation, also persisted;
- `generation_status` — inspect a prompt ID and reconcile history;
- `collect_generation` — wait/download an existing prompt and reconcile history;
- `read_output_image` — return an authorized generated file as native MCP image content for visual inspection;
- `task_history` — recent shared CLI + MCP generation history;
- `task_statistics` — shared task counts by status;
- `stop_managed_backend` — stop only identity-verified native ComfyUI started by EVAVO.

`generate_image` and `generate_batch` default to `auto_start=true` and `wait=true` for one-call agent workflows.

`read_output_image` is deliberately file-restricted: the file must be a supported image, non-empty, below the MCP payload cap, and either inside EVAVO's default output tree or present in EVAVO's recorded generation history.

## Shared task history

MCP and CLI generation use the same lock-protected, atomic history file:

```text
task_history.json
```

New records preserve task ID, prompt/project, status, backend mode, checkpoint, workflow path, output directory, all output URIs, errors and timestamps. Older minimal history files remain readable.

Override history location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\image-generation-history.json"
```

A Claude-generated task can therefore be inspected with `evavo.py tasks`, and a CLI-generated task appears through MCP `task_history`.

## Generated files

Agent downloads default to:

```text
<repo>\.evavo\outputs\<project>\
```

Override globally:

```powershell
$env:EVAVO_GENERATION_OUTPUT_DIR = "D:\EVAVO\generated"
```

## Custom ComfyUI API workflow

For Flux, SDXL variants, custom nodes, ControlNet or other pipelines export API-format JSON from ComfyUI and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\workflows\production-api.json"
```

Supported placeholders:

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

A generation call can also pass `workflow_path` explicitly.

## Agent doctor

Read-only diagnosis:

```powershell
python agent-doctor.py
```

Strict repair/readiness gate with provisioning:

```powershell
python agent-doctor.py --repair --provision
```

Native ComfyUI and at least one usable checkpoint are required for the built-in workflow. The command fails rather than reporting success on the deterministic mock fallback. It also validates configured shared roots and reports the common loader-node model inventory.

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

Offline provisioning/runtime tests verify traversal rejection, checkpoint copy/hash verification, idempotency, destination-conflict safety, HTTPS enforcement, source/portable layouts, shared-model YAML generation, config hashing, PID identity matching, and healthy source-runtime reuse without dependency reinstallation.

Agent tests verify MCP v2 in-process/stdio/Streamable HTTP negotiation, the advertised tool inventory, model inventory, mock rejection, image generation, batch generation, shared history/statistics, and native MCP image-content delivery.

Operational tests separately verify mock/native health, workflow submission, output history/downloads, rich batch tracking, legacy-history compatibility, offline behavior and controller lifecycle.

## Safety/lifecycle rules

- Native and MCP HTTP listeners are loopback by default.
- EVAVO never uses broad `taskkill /IM python.exe` cleanup.
- Managed native/mock shutdown verifies the recorded process command before termination; stale/reused PIDs are not trusted.
- An already-running user-managed ComfyUI is reused and is not stopped by EVAVO.
- Existing standard source/portable installs are reused before creating a new sibling checkout.
- Portable embedded Python is not modified by the provisioner.
- EVAVO-managed ComfyUI restarts only when needed to apply a changed EVAVO shared-model configuration.
- Output downloads use temporary files followed by atomic replacement.
- Legacy launchers are compatibility shims and no longer spawn persistent `cmd /k`, `-NoExit`, Ollama/Kokoro, or surprise multimodal jobs.
