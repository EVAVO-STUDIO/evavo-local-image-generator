# EVAVO Local Image Generator

A Windows-first local image-generation control plane for native ComfyUI, with one operational path shared by CLI automation, Claude Desktop and ChatGPT.

The repository no longer treats its deterministic mock as a renderer. Real agent generation requires native ComfyUI; the mock remains only for isolated operational/integration testing.

## What works

- native ComfyUI detection and health;
- source + Windows-portable ComfyUI discovery;
- optional official ComfyUI runtime provisioning;
- native checkpoint discovery and constrained checkpoint repair;
- shared external model libraries without copying multi-GB model files;
- checkpoint/LoRA/VAE/ControlNet/UNET/text-encoder/CLIP-vision/upscaler inventory;
- standard txt2img API workflow;
- custom ComfyUI API workflow templates;
- real `/prompt` submission and prompt IDs;
- `/history/<prompt_id>` completion tracking;
- `/view` output collection and atomic local downloads;
- bounded-concurrency batch generation;
- lock-protected atomic task history shared by CLI + MCP;
- MCP v2 over stdio and loopback Streamable HTTP;
- native MCP image content for generated-image inspection;
- Claude Desktop MCP installer;
- private HTTP MCP Windows-login autostart;
- OpenAI Secure MCP Tunnel tooling for real ChatGPT-to-workstation access;
- strict diagnostics, safety tests and recovery tooling.

## Canonical Windows setup

From the repository root:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

On an old checkout, update once first:

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater refuses destructive Git changes, installs dependencies, runs the repository test suites, configures local agent integrations, repairs/provisions native ComfyUI when allowed, validates checkpoint/shared-model readiness and configures the ChatGPT tunnel when a valid OpenAI tunnel ID is already available.

Useful switches:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipDependencies
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIProvision
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

## CLI generation

Real render, wait and download:

```powershell
python evavo.py generate `
  --prompts "PS1 horror corridor" `
  --project ps1 `
  --wait
```

Multiple prompts:

```powershell
python evavo.py generate `
  --prompts "corridor one" "corridor two" "corridor three" `
  --project ps1 `
  --wait
```

Custom destination:

```powershell
python evavo.py generate `
  --prompts "Victorian study" `
  --project interiors `
  --wait `
  --output-dir "D:\EVAVO\Generated"
```

## Claude Desktop

Claude uses local **stdio MCP** and can spawn EVAVO directly.

The canonical updater configures it automatically, or install only Claude with:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after the configuration changes.

## ChatGPT

ChatGPT does **not** connect directly to workstation `127.0.0.1`.

EVAVO keeps its MCP server private on:

```text
http://127.0.0.1:8765/mcp
```

and uses **OpenAI Secure MCP Tunnel** as the supported outbound bridge to ChatGPT.

After an OpenAI administrator has created/associated a tunnel and supplied a runtime key:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_0123456789abcdef0123456789abcdef"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"

.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

The installer dynamically resolves the latest public `openai/tunnel-client` release and verifies the downloaded Windows ZIP against the SHA-256 digest published in the release metadata before installing it.

Runtime-key login persistence uses current-user Windows DPAPI and never writes the plaintext key to Git, `.evavo`, Claude configuration or the Windows Startup command.

Full ChatGPT tunnel instructions:

```text
CHATGPT-TUNNEL.md
```

## MCP tools

Current agent tool surface:

```text
provision_backend
ensure_backend
health_check
discover_backends
list_checkpoints
model_inventory
generate_image
generate_batch
generation_status
collect_generation
read_output_image
task_history
task_statistics
stop_managed_backend
```

`generate_image` and `generate_batch` default to auto-starting the real backend and waiting for completed output files.

`read_output_image` returns an authorized generated image as native MCP image content so a host model can visually inspect the result instead of receiving only a Windows path.

## Native ComfyUI

Default endpoint:

```text
http://127.0.0.1:8188
```

Native routes used by EVAVO:

```text
GET  /system_stats
GET  /object_info/<loader-node>
POST /prompt
GET  /history/<prompt_id>
GET  /view?filename=...&subfolder=...&type=...
```

EVAVO prefers real ComfyUI over its deterministic test mock. An existing user-managed native ComfyUI is reused and never killed by EVAVO.

## Provisioning ComfyUI

Explicit provisioning:

```powershell
python provision-comfyui.py
```

EVAVO reuses an existing standard source/portable install before creating another checkout. Source runtimes use an isolated `.venv`; healthy existing source runtimes are reused after Torch/CUDA + entrypoint validation instead of reinstalling dependencies every time. Windows-portable embedded Python is not modified.

If no install exists, the provisioner clones:

```text
https://github.com/Comfy-Org/ComfyUI.git
```

The provisioner does not silently choose a diffusion model.

## Checkpoint repair

Preferred local model source:

```powershell
$env:EVAVO_CHECKPOINT_FILE = "D:\AI\Models\model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<optional expected sha256>"
$env:EVAVO_CHECKPOINT_NAME = "model.safetensors"
```

Explicit HTTPS source:

```powershell
$env:EVAVO_CHECKPOINT_URL = "https://example.com/model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<recommended expected sha256>"
```

Agent profiles enable constrained repair with:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

The built-in checkpoint workflow can repair from an owner-configured source. Custom UNET/Flux workflows do not trigger an unrelated checkpoint download merely because `CheckpointLoaderSimple` is empty.

## Shared model libraries

Point EVAVO at existing model roots instead of copying large model folders:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Alias:

```text
EVAVO_COMFYUI_MODEL_ROOTS
```

EVAVO maps only supported directories that actually exist and writes its own generated config:

```text
.evavo\extra-model-paths.yaml
```

Managed ComfyUI receives it via:

```text
--extra-model-paths-config <repo>\.evavo\extra-model-paths.yaml
```

ComfyUI's own configuration is not overwritten. The generated config is fingerprinted; a changed effective model layout restarts only an identity-verified EVAVO-managed ComfyUI.

## Model inventory

Agents can inspect the environment before selecting a workflow:

```text
model_inventory
```

Current loader categories:

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

## Custom ComfyUI workflows

Set a default exported API-format workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Uppercase and legacy lowercase placeholders are both supported:

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

## Task history

CLI and MCP share the same lock-protected atomic history:

```text
task_history.json
```

Records can include task ID, prompt/project, status, backend, checkpoint, workflow, output directory, every output path, errors and timestamps.

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

## Diagnostics

Operations/backend:

```powershell
python evavo.py doctor
python evavo.py status
```

Strict real-agent readiness:

```powershell
python agent-doctor.py --repair --provision
```

ChatGPT tunnel:

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

OpenAI `tunnel-client doctor` is treated as a **local preflight**, not standalone proof of ChatGPT workspace visibility. The running tunnel plus the OpenAI Platform/ChatGPT app connection complete that system.

## Tests

Canonical setup runs:

```powershell
python test-provisioning.py
python test-backend-automation.py
python test-chatgpt-tunnel.py
python test-agent-integration.py
python evavo.py test
```

The suites cover provisioning safety, source/portable handling, runtime reuse, shared-model config/hash behavior, PID identity, checkpoint repair boundaries, MCP file-read boundaries, tunnel secret/install contracts, MCP negotiation, model inventory, single/batch generation, native image content, history/statistics, mock/native health and controller lifecycle.

## Security

- ComfyUI remains loopback-only.
- Private EVAVO HTTP MCP remains loopback-only.
- ChatGPT access uses an outbound OpenAI Secure MCP Tunnel rather than public inbound exposure.
- OpenAI tunnel-client downloads are SHA-256 verified before installation.
- Runtime tunnel keys are never committed and optional login persistence uses Windows DPAPI.
- Signed checkpoint URLs are not persisted into generated agent configs/startup files.
- MCP provisioning tools cannot accept arbitrary repository/model URLs from the model.
- MCP image reads are limited to authorized generated output files.
- Managed-process termination verifies process identity; stale/reused PIDs are not trusted.
- EVAVO never broadly kills `python.exe` processes.

## Documentation

```text
AGENT-INTEGRATION.md
CHATGPT-TUNNEL.md
OPERATIONS-GUIDE.md
QUICK-REFERENCE.md
DEPLOYMENT-ACTIVE.md
```
