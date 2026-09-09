# Claude operating notes — EVAVO Local Image Generator

This repository is the verified **local image-generation control plane** for native ComfyUI. Claude should use the current MCP v2 tools or canonical CLI/controller and must not revive historical BeeStation, Ollama/Kokoro, fake multimodal, or source-regeneration paths.

## Preferred Claude interface

Claude Desktop uses local **stdio MCP**:

```text
python -m evavo_local_image_generator.mcp_server --transport stdio
```

The canonical installer writes absolute Python/repository paths and preserves existing MCP servers:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

The full workstation setup is:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

Restart Claude Desktop after its MCP configuration changes.

## MCP tool contract

Prefer these tools instead of shell orchestration:

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

Normal image requests should generally use `generate_image` or `generate_batch`. They default to auto-starting the native renderer and waiting for completed output files.

Use `workflow_preflight` before a custom exported ComfyUI API workflow when compatibility is uncertain. Use `model_inventory` to inspect available checkpoints/LoRAs/VAEs/ControlNet/UNET/text encoders/CLIP vision/upscalers.

Use `read_output_image` when the model needs the generated image as native MCP image content rather than only a local path.

## Runtime behavior

EVAVO can:

1. detect real native ComfyUI through `/system_stats`;
2. reject the deterministic EVAVO mock as a real renderer;
3. discover source or Windows-portable ComfyUI installs;
4. provision the official source runtime when explicitly enabled and missing;
5. use configured shared model roots through an EVAVO-owned `extra-model-paths.yaml`;
6. repair an owner-configured checkpoint source when the built-in workflow needs it;
7. start native ComfyUI without broad process killing;
8. submit `/prompt` workflows;
9. poll `/history/<prompt_id>`;
10. download `/view` outputs atomically;
11. persist task status/output metadata in the shared task history.

A user-managed ComfyUI is reused and never killed. EVAVO stops only identity-verified processes it manages.

## Native endpoint

Default:

```text
http://127.0.0.1:8188
```

Preferred environment variable:

```text
COMFYUI_ENDPOINT
```

`EVAVO_COMFYUI_ENDPOINT` remains a compatibility alias.

## Model/runtime configuration

Useful owner-controlled variables include:

```text
EVAVO_COMFYUI_HOME
EVAVO_COMFYUI_PYTHON
EVAVO_COMFYUI_SEARCH_PATHS
EVAVO_COMFYUI_CHECKPOINT
EVAVO_COMFYUI_WORKFLOW
EVAVO_SHARED_MODEL_ROOTS
EVAVO_CHECKPOINT_FILE
EVAVO_CHECKPOINT_URL
EVAVO_CHECKPOINT_SHA256
EVAVO_CHECKPOINT_NAME
EVAVO_AUTO_PROVISION_COMFYUI
EVAVO_AUTO_PROVISION_CHECKPOINT
EVAVO_GENERATION_OUTPUT_DIR
EVAVO_TASK_HISTORY
```

Do not invent/download a model source when none was configured by the workstation owner. The parameterless `provision_backend` MCP tool is deliberately constrained and accepts no arbitrary repository/model URL from the model.

## Custom workflows

Custom ComfyUI API-format workflows may use uppercase or legacy lowercase placeholders:

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

## Shared task history

CLI and MCP use the same lock-protected atomic history. A Claude-generated task can be inspected through `python evavo.py tasks`, and CLI tasks are visible through MCP `task_history`.

## Verification

Before changing workstation configuration or after a substantial repository update:

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

`verify-evavo.py` automatically discovers modern root/package test suites and checks supported compatibility entry points for retired dangerous behavior.

## Historical filenames

Files such as `run_autonomous.py`, `RUN-GENERATION.py`, `EVAVO-AUTOMATION.py`, `START-EVERYTHING.ps1`, and related launchers remain only for backwards compatibility. They delegate to the canonical image runtime. Do not treat them as separate service architectures.

`setup-production.py` and `create-complete-production.py` are non-destructive compatibility shims; historical source regeneration has been retired.

## Scope boundary

This repository does **not** claim verified production generation for video, audio, 3D models, particles, general text, or dedicated PBR textures. Historical placeholder/fake-success behavior has been removed or converted to explicit `NOT_IMPLEMENTED`/HTTP `501` responses.

Use the dedicated EVAVO repositories for those modalities.

## Security rules

- keep ComfyUI, MCP HTTP and the optional gateway on loopback;
- do not expose raw local ports publicly for ChatGPT;
- do not use blanket `taskkill /IM python.exe` or equivalent process cleanup;
- do not persist signed checkpoint URLs into agent startup profiles;
- do not print/store OpenAI tunnel runtime keys in repo files;
- use current-user DPAPI for optional persistent ChatGPT tunnel runtime-key storage;
- downloaded tunnel-client releases and the installed executable are SHA-256 verified before execution.

See `README.md`, `AGENT-INTEGRATION.md`, `OPERATIONS-GUIDE.md`, `CHATGPT-TUNNEL.md`, and `QUICK-REFERENCE.md` for current details.
