# EVAVO Local Image Generator — Current Project Summary

This repository is EVAVO's Windows-first **local image-generation control plane**. Its production renderer is native ComfyUI. The deterministic EVAVO mock exists only for isolated tests and explicit development use.

## Production scope

Verified production scope:

- native ComfyUI discovery, health and safe lifecycle management;
- optional official ComfyUI provisioning;
- checkpoint and broader model inventory;
- shared external model roots without copying model files;
- built-in checkpoint txt2img workflow;
- custom ComfyUI API-workflow template substitution and live preflight;
- real `/prompt` queue submission and ComfyUI prompt IDs;
- `/history/<prompt_id>` completion tracking;
- `/view` output collection with atomic local downloads;
- bounded-concurrency image batches;
- lock-protected atomic task history shared by CLI and MCP;
- MCP v2 over stdio and private loopback Streamable HTTP;
- native MCP image content for inspecting completed outputs;
- Claude Desktop installer/autostart integration;
- OpenAI Secure MCP Tunnel tooling for ChatGPT-to-workstation access;
- optional loopback HTTP gateway for compatibility clients;
- read-only repository verification plus Windows PowerShell AST checks.

Not claimed as production capabilities in this repository:

- video generation;
- audio/TTS/music/SFX generation;
- 3D model generation;
- particle-system generation;
- dedicated PBR texture-set generation;
- general-purpose LLM text generation.

Historical package imports for those modalities remain only as compatibility stubs and raise `UnsupportedGenerationError`/`NotImplementedError` rather than fabricating queued/completed results.

## Canonical operator path

On Windows:

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater fast-forwards `main`, installs required dependencies, runs the authoritative verifier, configures supported agent integrations, repairs/provisions native ComfyUI when permitted, and validates real generation readiness.

Repository verification:

```powershell
python evavo.py verify --full --require-powershell
```

Production bootstrap:

```powershell
python evavo.py bootstrap
```

`bootstrap` now requires a **native renderer** and passes `--no-mock`; the deterministic test mock cannot satisfy production bootstrap.

## Image generation

CLI:

```powershell
python evavo.py generate --prompts "EVAVO smoke image" --project smoke --wait
```

MCP exposes the current image tools through:

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

`COMFYUI_ENDPOINT` is the canonical endpoint environment variable. `EVAVO_COMFYUI_ENDPOINT` remains only as a fallback compatibility alias.

## Agent delivery

Claude Desktop:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Private local HTTP MCP:

```powershell
.\START-AGENT-MCP.ps1
```

Default private endpoint:

```text
http://127.0.0.1:8765/mcp
```

ChatGPT remote access uses the repository's OpenAI Secure MCP Tunnel tooling. Local MCP/ComfyUI/gateway listeners remain loopback-only rather than being directly exposed to the public Internet.

## Optional HTTP gateway

The compatibility gateway remains available at `127.0.0.1:8000` when explicitly started. It is intentionally image-only:

- `/generate/image` uses the real native ComfyUI path;
- `/generate/video`, `/generate/audio`, and `/generate/3d` return HTTP `501`;
- production gateway health requires native ComfyUI;
- the deterministic EVAVO mock cannot make the production gateway healthy.

## Verification architecture

`verify-evavo.py` is the authoritative repository verifier. It:

- checks critical files;
- compiles Python sources in memory;
- parses supported PowerShell scripts with the PowerShell AST when available/required;
- validates legacy launcher delegation and rejects retired active behavior;
- automatically discovers root `test-*.py`, root `test_*.py`, and package `tests/test_*.py` suites;
- includes isolated mock/native-ComfyUI simulations for deterministic integration testing;
- includes production-bootstrap, gateway, tunnel, Git-safety and unsupported-modality regressions.

## Git safety

Historical commit/push scripts now delegate to `safe_main_git.py` or perform read-only validation.

The safe helper:

- requires this repository and branch `main`;
- validates the reviewed `EVAVO-STUDIO/evavo-local-image-generator` origin;
- fetches and rejects behind/diverged history;
- runs the full verifier by default;
- rejects runtime/generated state from generic commits;
- rechecks the worktree after verification before staging;
- never deletes lock files or `.git`;
- never rewrites Git identity/remotes;
- never force-pushes;
- performs a normal `main:main` push and verifies the resulting remote SHA.

## State and outputs

Repository-owned runtime state lives under `.evavo/` and is ignored except for the intentionally tracked capability manifest:

```text
.evavo/capabilities.json
```

Generated images default under `.evavo/outputs/` unless a caller specifies another output directory. Shared task history is lock-protected and atomically written.

## Machine-readable capability authority

The current machine-readable repository capability description is:

```text
.evavo/capabilities.json
```

The old `evavo-repository-task-manifest.json` was removed because it described retired BeeStation/digest-bound multimodal architecture and nonexistent current tools.

## Current documentation authority

Use these files for current operation and architecture:

- `README.md`
- `CLAUDE.md`
- `AGENT-INTEGRATION.md`
- `OPERATIONS-GUIDE.md`
- `GATEWAY-INTEGRATION-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
- `DEPLOYMENT-CHECKLIST.md`

Files explicitly labeled historical/superseded are retained only for provenance and must not be used as current setup instructions.
