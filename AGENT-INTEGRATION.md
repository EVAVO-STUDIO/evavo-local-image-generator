# EVAVO Agent Integration

EVAVO exposes one native ComfyUI generation pipeline to Claude, ChatGPT through OpenAI Secure MCP Tunnel, local MCP clients, Codex/IDE agents, direct Python automation, and the `evavo.py` CLI.

## Canonical Windows setup

From a current checkout, the preferred setup is:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater now:

1. safely fast-forwards `main` without overwriting local changes;
2. parses every canonical PowerShell agent/tunnel script with PowerShell's AST parser before configuration writes;
3. installs/upgrades repository dependencies including `mcp[cli]>=2,<3`;
4. runs offline provisioning/runtime safety tests;
5. runs backend automation and MCP file-boundary tests;
6. runs ChatGPT tunnel security-contract tests;
7. runs negotiated MCP stdio + Streamable HTTP integration tests;
8. bootstraps/selects the generation backend;
9. installs/updates Claude Desktop stdio MCP configuration while preserving other servers;
10. installs the current-user private HTTP MCP login autostart;
11. runs `agent-doctor.py --repair --provision` as a strict real-generation readiness gate;
12. provisions official ComfyUI when no installation exists, unless disabled;
13. provisions an explicitly configured checkpoint source when the built-in workflow needs one;
14. validates shared model roots and the available ComfyUI model inventory;
15. verifies final backend status;
16. when a valid OpenAI tunnel ID already exists, configures the official OpenAI `tunnel-client` profile and starts the outbound ChatGPT bridge when a runtime key is available;
17. optionally installs persistent tunnel login startup when the runtime key has been stored with Windows DPAPI.

Troubleshooting switches:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIProvision
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

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
8. inject EVAVO-managed shared model roots without rewriting ComfyUI's own configuration;
9. restart only an identity-verified EVAVO-managed ComfyUI when that effective shared-model config changes;
10. wait for `/system_stats` readiness;
11. inspect available model-loader inventories;
12. auto-provision an owner-configured checkpoint when the built-in workflow needs one;
13. queue `/prompt` with the built-in or a custom API workflow;
14. poll `/history/<prompt_id>`;
15. download `/view` outputs atomically;
16. persist queue/completion/failure state plus backend/checkpoint/workflow/output metadata in shared task history;
17. return concrete local file paths;
18. optionally return an authorized generated image as native MCP image content through `read_output_image`.

## ComfyUI discovery

Automatic discovery covers common Windows locations, sibling Git repositories, source virtual environments and portable installs, including:

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

Non-standard installation:

```powershell
$env:EVAVO_COMFYUI_HOME = "D:\AI\ComfyUI"
```

Exact source interpreter:

```powershell
$env:EVAVO_COMFYUI_PYTHON = "D:\AI\ComfyUI\.venv\Scripts\python.exe"
```

Additional discovery roots can be supplied through `EVAVO_COMFYUI_SEARCH_PATHS` using the platform path separator.

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
- reuses a healthy existing source runtime after a Torch/CUDA probe and `main.py --help` smoke check rather than reinstalling dependencies;
- repairs/reinstalls source dependencies only when that runtime probe fails;
- detects NVIDIA and follows ComfyUI's documented stable CUDA PyTorch installation path;
- installs ComfyUI's own `requirements.txt` when required;
- records provisioning state in `.evavo/comfyui-provision.json`;
- does not silently select or license a diffusion model.

Agents can call the parameterless MCP tool:

```text
provision_backend
```

That tool intentionally accepts **no repository URL or arbitrary model URL argument**. It uses only the fixed EVAVO provisioner and model sources configured by the workstation owner.

Local agent profiles set:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

Checkpoint auto-repair still does nothing unless `EVAVO_CHECKPOINT_FILE` or `EVAVO_CHECKPOINT_URL` was explicitly configured by the workstation owner.

## Checkpoint provisioning

A real checkpoint is a blocking requirement for the built-in checkpoint-based txt2img workflow. EVAVO does not guess or silently choose a model source.

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

To reuse an existing model library instead of copying large files:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

`EVAVO_COMFYUI_MODEL_ROOTS` is accepted as an alias. Multiple roots use the operating-system path separator (`;` on Windows).

EVAVO maps only supported model directories that actually exist, including common locations for checkpoints, LoRAs/LyCORIS, VAE, text encoders/CLIP, diffusion models/UNET, CLIP vision, ControlNet/t2i adapters, embeddings, upscalers, custom nodes, and other ComfyUI categories.

EVAVO writes its own generated file:

```text
.evavo\extra-model-paths.yaml
```

Managed ComfyUI is launched with:

```text
--extra-model-paths-config <repo>\.evavo\extra-model-paths.yaml
```

EVAVO does **not** edit or replace ComfyUI's own `extra_model_paths.yaml`.

The effective generated YAML is SHA-256 fingerprinted in managed runtime state. If that configuration changes while an EVAVO-managed ComfyUI is running, EVAVO verifies the recorded process identity and restarts only that managed process. A user-managed ComfyUI is never killed; EVAVO instead reports that it cannot prove whether the requested extra model roots were loaded.

## Model inventory

Agents can inspect what ComfyUI actually exposes through loader nodes before choosing a workflow:

```text
model_inventory
```

Current categories include:

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

Each category is queried independently. Missing optional loader nodes are reported per category without breaking checkpoint generation. `agent-doctor.py` also summarizes these inventories.

## Claude Desktop: local stdio MCP

Install/update only the Claude integration:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude Desktop spawns EVAVO locally over stdio MCP. The installer resolves the actual Python/repository paths, validates integration by default, backs up the existing Claude config, preserves other MCP servers, enables constrained ComfyUI/checkpoint repair, and persists local non-secret model/workflow/shared-root settings.

Restart Claude Desktop after changing its MCP configuration.

## Private Streamable HTTP MCP

EVAVO also exposes a private loopback Streamable HTTP listener for local clients, integration testing, and as the **private target of the ChatGPT tunnel**.

Manual foreground start:

```powershell
.\START-AGENT-MCP.ps1
```

Install current-user Windows login autostart and start it now:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

Default private endpoint:

```text
http://127.0.0.1:8765/mcp
```

The listener is loopback-only, uses exact host/origin allowlists for its configured port, and enables DNS-rebinding protection. Do not expose this listener or ComfyUI directly to the public internet.

## ChatGPT: OpenAI Secure MCP Tunnel

ChatGPT cloud cannot directly reach workstation `127.0.0.1`. The supported EVAVO production bridge is the official OpenAI Secure MCP Tunnel, which makes an outbound connection from the workstation while the EVAVO MCP server stays private on localhost.

One-time OpenAI-side prerequisite: create/associate a tunnel for the intended workspace and obtain its ID. EVAVO expects the exact ID shape:

```text
tunnel_<32 lowercase hexadecimal characters>
```

Configure the workstation:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key for this shell>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

Or simply rerun the canonical updater once the tunnel ID/runtime key are available. The updater will finish the tunnel profile and start it automatically.

Important security behavior:

- `tunnel-client` is downloaded only from the official `openai/tunnel-client` latest GitHub release;
- the published release-asset SHA-256 digest is verified before extraction;
- EVAVO uses OpenAI's HTTP DCR sample profile and points it at the private `127.0.0.1` MCP endpoint;
- the runtime key is never committed, written to `.evavo/chatgpt-tunnel.json`, or embedded into Windows Startup;
- persistent login startup requires the key to be stored using Windows current-user DPAPI under `%LOCALAPPDATA%\EVAVO\Secure`;
- an ephemeral process-environment key can start the tunnel for the current session but is not treated as reboot-persistent;
- `CHATGPT-TUNNEL-DOCTOR.ps1` distinguishes profile/local preflight/process state and does **not** claim that a successful local doctor alone proves ChatGPT workspace visibility.

Commands:

```powershell
.\SAVE-CHATGPT-TUNNEL-KEY.ps1 -FromEnvironment
.\START-CHATGPT-MCP-TUNNEL.ps1
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

See `CHATGPT-TUNNEL.md` for the dedicated tunnel runbook.

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
- `read_output_image` — return an authorized generated file as native MCP image content;
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

Records preserve task ID, prompt/project, status, backend mode, checkpoint, workflow path, output directory, output URIs, errors, and timestamps while remaining compatible with older minimal records.

Override history location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\image-generation-history.json"
```

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

For Flux, SDXL variants, custom nodes, ControlNet or other pipelines, export API-format JSON from ComfyUI and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\workflows\production-api.json"
```

EVAVO accepts both the current uppercase placeholders and the older lowercase forms for backward compatibility:

```text
{{PROMPT}} / {{prompt}}
{{NEGATIVE_PROMPT}} / {{negative_prompt}}
{{WIDTH}} / {{width}}
{{HEIGHT}} / {{height}}
{{STEPS}} / {{steps}}
{{CFG}} / {{CFG_SCALE}} / {{cfg}} / {{cfg_scale}}
{{SEED}} / {{seed}}
{{CHECKPOINT}} / {{checkpoint}}
{{FILENAME_PREFIX}} / {{filename_prefix}}
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

Native ComfyUI and at least one usable checkpoint are required for the built-in workflow. The deterministic mock cannot satisfy the strict real-renderer gate. The doctor also validates configured shared roots and reports common loader-node model inventory.

## Validation

The full workstation updater runs:

```powershell
python test-provisioning.py
python test-backend-automation.py
python test-chatgpt-tunnel.py
python test-agent-integration.py
python evavo.py test
```

It also parses the canonical PowerShell installer/launcher scripts with PowerShell's AST parser before making agent/tunnel configuration changes.

The suites cover provisioning idempotency and checkpoint safety, shared-model YAML/config hashes, PID identity checks, backend checkpoint repair, MCP output-file authorization, ChatGPT tunnel SHA/key/state contracts, MCP stdio/Streamable HTTP negotiation, model inventory, mock rejection, image/batch generation, shared history/statistics, image-content delivery, native workflow submission/output collection, offline behavior, and controller lifecycle.

## Safety/lifecycle rules

- Native and private MCP HTTP listeners bind to loopback by default.
- The ChatGPT bridge uses an outbound OpenAI Secure MCP Tunnel rather than opening an inbound public MCP/ComfyUI port.
- EVAVO never uses broad `taskkill /IM python.exe` cleanup.
- Managed native/mock shutdown verifies the recorded process command before termination; stale/reused PIDs are not trusted.
- An already-running user-managed ComfyUI is reused and is not stopped by EVAVO.
- Existing standard source/portable installs are reused before creating a new sibling checkout.
- Portable embedded Python is not modified by the provisioner.
- EVAVO-managed ComfyUI restarts only when needed to apply changed EVAVO shared-model configuration.
- Output downloads use temporary files followed by atomic replacement.
- Tunnel runtime keys are not stored in Git/repository state/Startup plaintext.
- Legacy launchers are compatibility shims and no longer spawn persistent `cmd /k`, `-NoExit`, Ollama/Kokoro, or surprise multimodal jobs.
