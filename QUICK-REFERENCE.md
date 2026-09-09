# EVAVO Local Image Generator - Quick Reference

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Current checkout:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Troubleshooting switches:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipAgentConfiguration
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipComfyUIProvision
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

## Verification

```powershell
python evavo.py verify
python evavo.py verify --full
python evavo.py verify --full --require-powershell
```

`verify --full` auto-discovers maintained root, `tests/`, and package suites.

## Real-agent readiness

```powershell
python agent-doctor.py
python agent-doctor.py --repair --provision
python agent-doctor.py --repair --provision --json
```

The strict gate requires a native renderer and the active workflow/model contract. The deterministic mock does not satisfy it.

## Aggregate read-only status

```powershell
.\AGENT-STATUS.ps1
.\AGENT-STATUS.ps1 -Json
```

Optional gateway/provider readiness is reported separately from owned native-image readiness.

## Claude

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses local stdio MCP. Restart Claude Desktop after config changes.

## Private HTTP MCP

```powershell
.\START-AGENT-MCP.ps1
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

```text
http://127.0.0.1:8765/mcp
```

Loopback only; do not expose it publicly.

## ChatGPT

Cloud ChatGPT uses the outbound OpenAI Secure MCP Tunnel rather than direct workstation localhost.

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

See `CHATGPT-TUNNEL.md`.

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

`generate_image` / `generate_batch` auto-start and wait by default.

Invalid file/wait policy is rejected before backend startup and before queueing.

## MCP output policy

Default generated-output root:

```text
<repo>\.evavo\outputs\
```

Override default:

```powershell
$env:EVAVO_GENERATION_OUTPUT_DIR = "D:\EVAVO\generated"
```

Additional owner-approved roots:

```powershell
$env:EVAVO_MCP_OUTPUT_ROOTS = "D:\EVAVO\ProjectA;E:\ApprovedRenders"
```

A tool-supplied `output_dir` outside approved roots is rejected.

`read_output_image` requires an authorized ordinary PNG/JPEG/GIF/WebP file, rejects symlinked/redirected paths and validates the image file signature.

## MCP custom workflow policy

Preferred owner default:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "D:\EVAVO\workflows\production-api.json"
```

Tool-supplied workflow paths are disabled by default. To expose only a reviewed workflow library:

```powershell
$env:EVAVO_MCP_ALLOW_WORKFLOW_PATHS = "1"
$env:EVAVO_MCP_WORKFLOW_ROOT = "D:\EVAVO\workflows\approved"
```

Files outside that root, symlinks and redirected parent paths are rejected.

Claude and HTTP-login installers persist these approved **non-secret** path-policy values when configured.

## CLI image generation

```powershell
# Queue
python evavo.py generate --prompts "PS1 horror corridor" --project ps1

# Wait + download
python evavo.py generate --prompts "PS1 horror corridor" --project ps1 --wait

# Batch
python evavo.py generate --prompts "corridor one" "corridor two" --project ps1 --wait

# CLI custom destination (CLI policy is separate from MCP file authority)
python evavo.py generate --prompts "PS1 corridor" --project ps1 --wait --output-dir "C:\EVAVO\Generated"
```

## Workflow preflight

MCP:

```text
workflow_preflight
```

Custom workflows are also preflighted automatically before `/prompt` unless `EVAVO_PREFLIGHT_CUSTOM_WORKFLOW=0` is explicitly set for an unusual graph.

Supported template placeholders include:

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

## ComfyUI provisioning

```powershell
python provision-comfyui.py
```

Owner-configured checkpoint repair:

```powershell
$env:EVAVO_CHECKPOINT_FILE = "D:\AI\Models\model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<optional sha256>"
$env:EVAVO_CHECKPOINT_NAME = "model.safetensors"
```

or HTTPS:

```powershell
$env:EVAVO_CHECKPOINT_URL = "https://example.com/model.safetensors"
$env:EVAVO_CHECKPOINT_SHA256 = "<recommended sha256>"
```

Agent profiles can enable:

```text
EVAVO_AUTO_PROVISION_COMFYUI=1
EVAVO_AUTO_PROVISION_CHECKPOINT=1
```

MCP provisioning does not accept arbitrary model/repository URLs from a tool call.

## Shared model libraries

```powershell
$env:EVAVO_SHARED_MODEL_ROOTS = "D:\AI\Models;E:\SharedModels"
```

Alias:

```text
EVAVO_COMFYUI_MODEL_ROOTS
```

EVAVO writes `.evavo\extra-model-paths.yaml` and passes it to managed ComfyUI; it does not overwrite ComfyUI's own configuration.

## Model inventory

MCP:

```text
model_inventory
```

Categories include checkpoints, LoRAs, VAEs, ControlNet, diffusion/UNET models, text encoders, CLIP vision and upscalers.

## Shared task history

```powershell
python evavo.py tasks --limit 20
python evavo.py stats
```

Override location:

```powershell
$env:EVAVO_TASK_HISTORY = "D:\EVAVO\state\image-generation-history.json"
```

## Optional HTTP gateway

```powershell
.\START-GATEWAY.ps1
python EVAVO-SERVICE-MANAGER.py health
```

Default:

```text
http://127.0.0.1:8000
```

Owned:

```text
POST /generate/image
```

Optional delegated:

```text
POST /generate/video
POST /generate/audio
POST /generate/3d
```

Readiness:

```text
GET /services
GET /capabilities
```

`202` means accepted, not completed. Missing providers fail with `PROVIDER_*` task errors.

Gateway security:

- loopback-only;
- CORS off by default; wildcard/non-loopback origins rejected;
- pre-parse request-size cap including chunked bodies;
- per-request workflow paths disabled by default and owner-root confined when enabled;
- recorded result paths must remain ordinary non-redirected files;
- corrupt task state fails closed;
- one live gateway owner per task-state file;
- service-manager state and lifecycle operations are cross-process serialized;
- process stops remain identity verified.

See `GATEWAY-INTEGRATION-GUIDE.md` and `GATEWAY-AUX-PROVIDERS.md`.

## Recovery

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

Then see `AGENT-RECOVERY.md` if a specific Claude/MCP/tunnel/gateway process needs recovery.
