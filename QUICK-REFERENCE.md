# EVAVO Local Image Generator - Quick Reference

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater safely fast-forwards `main`, parses canonical PowerShell scripts before configuration writes, installs dependencies, runs all offline/integration suites, configures Claude + private HTTP MCP, provisions/repairs ComfyUI when allowed, validates the active generation contract, and configures the ChatGPT Secure MCP Tunnel when a valid tunnel ID is already available.

Troubleshooting switches:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIProvision
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

## Repository verification

Fast read-only structural/Python/PowerShell-when-available verification:

```powershell
python evavo.py verify
```

Full repository contract plus all Python safety/integration suites:

```powershell
python evavo.py verify --full
```

Require a real PowerShell parser rather than allowing that one platform-specific check to be skipped:

```powershell
python evavo.py verify --full --require-powershell
```

`verify-evavo.py` compiles Python sources in memory and does not create `__pycache__` as part of syntax checking.

## Agent readiness

```powershell
python agent-doctor.py
python agent-doctor.py --repair --provision
python agent-doctor.py --repair --provision --json
```

Strict repair requires a real native ComfyUI plus a usable **active generation contract**:

- with no `EVAVO_COMFYUI_WORKFLOW`, the built-in checkpoint workflow requires a usable checkpoint;
- with `EVAVO_COMFYUI_WORKFLOW` configured, that custom workflow is rendered and preflighted against live ComfyUI nodes/models, and checkpoint absence is non-blocking unless that workflow itself requires one.

A healthy externally started ComfyUI is reused even when its filesystem install is not discoverable. EVAVO does not clone a second runtime merely because discovery cannot locate the already-running renderer.

The deterministic mock cannot satisfy the strict real-renderer gate. The doctor also validates shared model roots and reports checkpoint/LoRA/VAE/ControlNet/UNET/text-encoder/CLIP-vision/upscaler inventories.

## Claude Desktop

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses **local stdio MCP**. Restart Claude Desktop after changing its config.

## Private local HTTP MCP

```text
http://127.0.0.1:8765/mcp
```

```powershell
.\START-AGENT-MCP.ps1
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

This listener is loopback-only. It is for local MCP clients, integration testing, and as the private target of the ChatGPT tunnel. It is **not** directly reachable by cloud ChatGPT and should not be publicly exposed.

## ChatGPT Secure MCP Tunnel

ChatGPT reaches EVAVO through the official outbound OpenAI Secure MCP Tunnel, not by connecting directly to workstation localhost.

One-time prerequisite: obtain/associate a tunnel ID for the intended OpenAI workspace. EVAVO validates the exact shape:

```text
tunnel_<32 lowercase hexadecimal characters>
```

Configure/start:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

Diagnostics:

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

Session-only start without persisting the runtime key:

```powershell
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel key>"
.\START-CHATGPT-MCP-TUNNEL.ps1
```

Persistent login startup requires the runtime key to be stored with Windows current-user DPAPI:

```powershell
.\SAVE-CHATGPT-TUNNEL-KEY.ps1 -FromEnvironment
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

The installer downloads the latest official `openai/tunnel-client` Windows release, verifies the SHA-256 digest published in GitHub release metadata before extraction, records the extracted executable SHA-256, and rechecks that executable before every tunnel run. The runtime key is never stored in Git, `.evavo/chatgpt-tunnel.json`, or Windows Startup plaintext.

`CHATGPT-TUNNEL-DOCTOR.ps1` is a local preflight/process diagnostic. It deliberately does not claim that a passing local doctor alone proves ChatGPT workspace visibility.

See `CHATGPT-TUNNEL.md` for the full runbook.

## MCP tools

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

`workflow_preflight` is read-only: it renders a custom API workflow with the same substitution path used by generation, checks live ComfyUI node classes/required inputs/literal model choices, and returns structured compatibility diagnostics **without queueing work or writing task history**.

`generate_image` / `generate_batch` auto-start and wait by default. Custom workflows are preflighted automatically before `/prompt`; set `EVAVO_PREFLIGHT_CUSTOM_WORKFLOW=0` only as an explicit escape hatch for unusual graphs. `read_output_image` returns an authorized generated file as native MCP image content so an agent can visually inspect it.

## Real image generation

```powershell
# Queue
python evavo.py generate --prompts "PS1 horror corridor" --project ps1

# Render + wait + download
python evavo.py generate --prompts "PS1 horror corridor" --project ps1 --wait

# Multiple prompts
python evavo.py generate --prompts "corridor one" "corridor two" --project ps1 --wait

# Custom destination
python evavo.py generate --prompts "PS1 corridor" --project ps1 --wait --output-dir "C:\EVAVO\Generated"

# Custom ComfyUI API workflow
python evavo.py generate --prompts "PS1 corridor" --workflow "C:\EVAVO\workflows\workflow-api.json" --wait
```

For Claude/ChatGPT, call `workflow_preflight` on a custom workflow before a long batch when you want explicit compatibility diagnostics up front.

## Runtime/model provisioning

```powershell
python provision-comfyui.py
```

Healthy source runtimes are reused after Torch/CUDA + ComfyUI entrypoint validation. Windows-portable installations are reused without modifying embedded Python.

Configured checkpoint repair:

```powershell
$env:EVAVO_CHECKPOINT_FILE = "D:\AI\Models\model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<optional sha256>"
$env:EVAVO_CHECKPOINT_NAME = "model.safetensors"
```

or an explicit HTTPS source:

```powershell
$env:EVAVO_CHECKPOINT_URL = "https://example.com/model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<recommended sha256>"
```

Local agent profiles enable:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

Checkpoint repair uses only workstation-configured sources. Custom UNET/Flux workflows do not trigger checkpoint provisioning merely because `CheckpointLoaderSimple` is empty or absent.

## Shared model libraries

Reuse existing model folders without copying multi-GB files:

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Alias: `EVAVO_COMFYUI_MODEL_ROOTS`.

EVAVO detects existing model subfolders and writes only its own generated file:

```text
.evavo\extra-model-paths.yaml
```

Managed ComfyUI is launched with `--extra-model-paths-config` pointing at that file. ComfyUI's own configuration is never overwritten. If the effective EVAVO model-path config changes, only an identity-verified EVAVO-managed ComfyUI is restarted; user-managed ComfyUI processes are never killed.

## Model inventory

MCP:

```text
model_inventory
```

CLI/diagnostic:

```powershell
python evavo.py doctor
python agent-doctor.py --repair --provision
```

Inventory categories currently cover checkpoints, LoRAs, VAEs, ControlNet, diffusion/UNET models, text encoders, CLIP vision and upscalers.

## Shared history

CLI and MCP use the same atomic lock-protected history:

```text
task_history.json
```

Records preserve backend/checkpoint/workflow/output metadata and all output paths while remaining compatible with older minimal records.

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

Override:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\image-generation-history.json"
```

## Controller

| Operation | Command |
|---|---|
| Diagnose operations/models | `python evavo.py doctor` |
| Verify repo contracts | `python evavo.py verify` |
| Full contract/tests | `python evavo.py verify --full` |
| Strict agent repair | `python agent-doctor.py --repair --provision` |
| Sync `main` | `python evavo.py sync` |
| Full bootstrap | `python evavo.py bootstrap` |
| Native-only start | `python evavo.py start --no-mock` |
| Backend status | `python evavo.py status` |
| Render batch | `python evavo.py generate --prompts "one" "two" --project demo --wait` |
| Tasks | `python evavo.py tasks --limit 20` |
| Statistics | `python evavo.py stats` |
| Operational tests | `python evavo.py test` |
| Agent/MCP tests | `python test-agent-integration.py` |
| Workflow-aware doctor tests | `python test-agent-doctor-workflows.py` |
| Provision/runtime safety | `python test-provisioning.py` |
| Backend/file-boundary safety | `python test-backend-automation.py` |
| ChatGPT tunnel contracts | `python test-chatgpt-tunnel.py` |
| Stop EVAVO-owned processes | `python evavo.py stop` |

## Custom workflow placeholders

Current uppercase and legacy lowercase forms are both accepted:

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

Set default workflow:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\EVAVO\workflows\workflow-api.json"
```

## State/output files

```text
.evavo/operations-service.json       EVAVO-owned mock state
.evavo/mock-service.log              mock log
.evavo/native-comfyui-service.json   managed native PID/config state
.evavo/native-comfyui.log            native startup log
.evavo/comfyui-provision.json        provisioning result
.evavo/extra-model-paths.yaml        EVAVO-managed shared model config
.evavo/chatgpt-tunnel.json           non-secret tunnel/profile state
.evavo/tools/tunnel-client.exe       verified official tunnel client
.evavo/outputs/                      default downloaded images
task_history.json                    shared CLI + MCP history
task_history.json.lock               inter-process lock
```

Persistent tunnel runtime key (outside the repository):

```text
%LOCALAPPDATA%\EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi
```

## Recovery

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py doctor
python monitor-evavo.py --json
python test-agent-doctor-workflows.py
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
Get-Content .\.evavo\native-comfyui.log -Tail 100
Get-Content .\.evavo\mock-service.log -Tail 100
```

Python 3.10+ already includes `asyncio`. Do **not** install the separate PyPI `asyncio` package.

Do **not** use broad `taskkill /IM python.exe`; EVAVO verifies managed process identity before termination.
