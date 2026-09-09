# EVAVO Agent Integration

EVAVO exposes one owned production generation capability from this repository: **local image generation through native ComfyUI**. Claude, ChatGPT, local MCP clients, IDE agents, direct Python automation and `evavo.py` share the same renderer/lifecycle/task-history contract.

The deterministic EVAVO mock is test infrastructure and cannot satisfy production readiness.

The optional loopback HTTP gateway can also **delegate** video, audio and 3D jobs to separately governed sibling EVAVO Studio providers. Those delegated routes are not MCP/package-owned capabilities of this image-generator repository.

## Canonical Windows convergence

From the repository root:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

For a stale clean checkout:

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater fast-forwards `main`, parses canonical PowerShell scripts before configuration writes, installs dependencies, runs the authoritative verifier, configures Claude/private HTTP MCP, repairs or provisions native ComfyUI when allowed, validates the active workflow/model contract, and conditionally configures the ChatGPT Secure MCP Tunnel when its OpenAI tunnel identity exists.

Authoritative verification:

```powershell
python evavo.py verify --full --require-powershell
```

The verifier automatically discovers the maintained root, `tests/`, and package test surfaces. Do not maintain a second hand-written test list.

## Agent lifecycle contract

An agent should not need to understand how ComfyUI was installed. A normal image request can:

1. validate the request/file policy before backend work;
2. reject the deterministic EVAVO mock as a renderer;
3. reuse a healthy native ComfyUI already running;
4. discover source or Windows-portable installations;
5. provision the fixed official ComfyUI source runtime when owner policy allows it;
6. load owner-configured shared model roots;
7. start native ComfyUI when installed but offline;
8. inventory live loader/model choices;
9. preflight a custom API workflow when configured;
10. submit `/prompt` and retain the real ComfyUI prompt ID;
11. poll `/history/<prompt_id>`;
12. collect `/view` image outputs atomically;
13. persist queue/completion/failure evidence in shared task history;
14. return local file paths and, when requested, native MCP image content.

An invalid path, timeout or file-policy request is rejected **before ComfyUI is started or a prompt is queued**. Invalid preflight-only requests do not create synthetic generation tasks.

## MCP tools

Current MCP tool surface:

```text
provision_backend
ensure_backend
health_check
discover_backends
list_checkpoints
model_inventory
workflow_preflight
generate_image
generate_batch
generation_status
collect_generation
read_output_image
task_history
task_statistics
stop_managed_backend
```

There are intentionally no `generate_video`, `generate_audio` or `generate_3d` MCP tools in this repository.

`generate_image` and `generate_batch` default to `auto_start=true` and `wait=true` for one-call agent workflows. Batch execution is concurrency bounded.

## MCP filesystem authority

MCP generation is **not arbitrary filesystem write/read authority**.

Default generated-output root:

```text
<repo>\.evavo\outputs\
```

Configured by:

```text
EVAVO_GENERATION_OUTPUT_DIR
```

A caller-provided `output_dir` must remain under that root unless the workstation owner explicitly adds existing approved roots:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\Generated;E:\ApprovedProjectRenders"
```

`EVAVO_MCP_OUTPUT_ROOTS` is owner configuration, not an MCP tool argument.

Output files returned through `read_output_image` must:

- be ordinary files, not symlinks;
- not traverse redirected/symlinked parent paths;
- be PNG/JPEG/GIF/WebP;
- contain a matching image file signature, not merely a trusted extension;
- be non-empty and within the MCP payload cap;
- be inside the default EVAVO output root or exactly recorded in EVAVO generation history.

This prevents a generated path from being replaced with a link to an unrelated local file and then read back through MCP.

## Custom workflow authority

The preferred production custom-workflow configuration is owner-side:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

The owner-configured default is validated as an ordinary file before use.

Tool-supplied `workflow_path` is **disabled by default**. To allow agents to choose among a reviewed workflow library, configure both:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

Then a tool-supplied workflow must be an ordinary file under that root. Symlinked files and redirected parent paths are rejected.

Do not give a model a broad root such as `C:\`, a user profile, the whole repository tree or another sensitive filesystem root.

Current and legacy workflow placeholders are both supported:

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

`workflow_preflight` validates live node classes, required inputs and literal loader/model choices without queueing a prompt or writing task history.

## Persistent agent profiles

The Claude Desktop installer and private HTTP MCP login-autostart installer preserve approved **non-secret** file-policy configuration:

```text
EVAVO_MCP_OUTPUT_ROOTS
EVAVO_MCP_ALLOW_WORKFLOW_PATHS
EVAVO_MCP_WORKFLOW_ROOT
```

They also preserve other safe local model/runtime settings. `EVAVO_CHECKPOINT_URL` is deliberately not copied into generated profiles/startup commands because signed model URLs can contain credentials.

Claude setup:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after configuration changes.

Private HTTP MCP setup:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

Default private endpoint:

```text
http://127.0.0.1:8765/mcp
```

The listener is loopback-only and uses exact host/origin allowlists plus MCP DNS-rebinding protection.

## ChatGPT

Cloud ChatGPT does not directly reach workstation `127.0.0.1`. EVAVO uses the official **OpenAI Secure MCP Tunnel** as the outbound bridge while the MCP server remains private.

See:

```text
CHATGPT-TUNNEL.md
```

Typical workstation setup after an OpenAI tunnel has been created/associated:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

Tunnel-client downloads are release-SHA verified. The installed executable is SHA-verified before runs. Optional persistent runtime-key storage uses current-user Windows DPAPI; the plaintext key is not stored in Git, `.evavo`, Claude configuration or Windows Startup.

## ComfyUI provisioning and discovery

EVAVO discovers common source/portable locations plus explicit owner configuration:

```text
EVAVO_COMFYUI_HOME
EVAVO_COMFYUI_PYTHON
EVAVO_COMFYUI_SEARCH_PATHS
```

Explicit provisioning:

```powershell
python provision-comfyui.py
```

The provisioner reuses existing reviewed installs, uses an isolated source `.venv`, does not modify a Windows-portable embedded Python runtime, and does not silently select/license a model.

Agent profiles can enable constrained repair:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

Checkpoint repair only uses owner-configured sources such as `EVAVO_CHECKPOINT_FILE` or `EVAVO_CHECKPOINT_URL`. MCP tools cannot supply arbitrary model/repository URLs.

## Shared model libraries

Reuse existing models without copying them:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Alias:

```text
EVAVO_COMFYUI_MODEL_ROOTS
```

EVAVO generates its own `.evavo\extra-model-paths.yaml` and passes it to managed ComfyUI with `--extra-model-paths-config`. It does not overwrite ComfyUI's own configuration. Effective model-path configuration is fingerprinted; only an identity-verified EVAVO-managed ComfyUI may be restarted when that configuration changes.

`model_inventory` reports common loader categories independently:

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

## Shared task history

CLI and MCP use the same atomic lock-protected task history. Records can include task ID, prompt/project, status, backend mode, checkpoint, workflow path, output directory, all output URIs, errors and timestamps.

Typical commands:

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

An alternate history path can be set with `EVAVO_TASK_HISTORY`.

## Optional HTTP gateway

The optional gateway is separate from MCP and remains loopback-only at:

```text
http://127.0.0.1:8000
```

Owned route:

```text
POST /generate/image -> native ComfyUI
```

Optional delegated routes:

```text
POST /generate/video
POST /generate/audio
POST /generate/3d
```

Use `GET /services` to inspect delegated provider readiness. A missing provider fails the asynchronous task with a structured `PROVIDER_*` error; `202` means accepted, not completed.

Gateway protections include CORS-off-by-default, pre-parse request size limits (including chunked bodies), owner-root-confined optional request workflows, ordinary-file result identity checks, fail-closed corrupt state and one live gateway owner per task-state file.

See `GATEWAY-INTEGRATION-GUIDE.md` and `GATEWAY-AUX-PROVIDERS.md`.

## Diagnosis and recovery

Read-only status:

```powershell
.\AGENT-STATUS.ps1
.\AGENT-STATUS.ps1 -Json
```

Strict image-runtime repair:

```powershell
python agent-doctor.py --repair --provision
```

Recovery runbook:

```text
AGENT-RECOVERY.md
```

No recovery path should broadly kill `python.exe`, overwrite `.git`, force-push, expose local generation ports publicly, or regenerate current source from historical templates.
