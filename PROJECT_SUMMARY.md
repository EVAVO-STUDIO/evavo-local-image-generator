# EVAVO Local Image Generator — Current Project Summary

This repository is EVAVO's Windows-first **local image-generation control plane**. Its owned production renderer is native ComfyUI. The deterministic EVAVO mock exists only for isolated tests and explicit development use.

## Owned production scope

Verified production scope owned by this repository:

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

The MCP/package generation surface remains **image-only**.

## Optional governed gateway delegation

The optional HTTP gateway may delegate these media types to separately governed sibling EVAVO Studio providers:

- video;
- audio;
- 3D.

This is delegation, not ownership transfer. Those modalities are not added to this repository's MCP tools or Python image-generation contract.

The delegated provider layer is fail-closed:

- readiness is visible through `/services` and `/capabilities`;
- provider commands use argument arrays rather than `shell=True`;
- success requires a JSON receipt plus a real admitted artifact;
- outputs are confined to task workspaces;
- generic receipt SHA-256 values are verified when supplied;
- the Wan provider verifies its model/output receipt hashes;
- the 3D worker is loopback-only, token-gated and workspace-confined;
- absent/misconfigured providers produce structured `PROVIDER_*` failures rather than fake files.

Still not owned production modalities in this repository include video, audio, 3D, particles, general text and dedicated PBR texture-set generation.

Historical package imports for non-image modalities remain only as compatibility stubs and raise `UnsupportedGenerationError`/`NotImplementedError` instead of fabricating queued/completed results.

## Canonical operator path

On Windows:

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater fast-forwards `main`, installs required dependencies, runs the authoritative verifier, configures supported agent integrations, repairs/provisions native ComfyUI when permitted, and validates real image-generation readiness.

Repository verification:

```powershell
python evavo.py verify --full --require-powershell
```

Production bootstrap:

```powershell
python evavo.py bootstrap
```

`bootstrap` requires a **native renderer** and passes `--no-mock`; the deterministic test mock cannot satisfy production bootstrap.

## Image generation

CLI:

```powershell
python evavo.py generate --prompts "EVAVO smoke image" --project smoke --wait
```

MCP exposes the current owned image tools:

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

`COMFYUI_ENDPOINT` is canonical. `EVAVO_COMFYUI_ENDPOINT` remains a fallback compatibility alias.

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

ChatGPT remote access uses the OpenAI Secure MCP Tunnel tooling. Local MCP/ComfyUI/gateway listeners remain loopback-only rather than being exposed directly to the public Internet.

Unified read-only diagnostics:

```powershell
.\AGENT-STATUS.ps1
```

Owned image readiness controls that command's exit status; optional gateway/provider readiness is reported separately.

## Optional HTTP gateway

Default:

```text
http://127.0.0.1:8000
```

Owned image route:

```text
POST /generate/image
```

Optional delegated routes:

```text
POST /generate/video
POST /generate/audio
POST /generate/3d
```

All generation routes are asynchronous and return `202` when accepted. `202` is not completion. Unavailable auxiliary providers fail their task with a structured provider error.

Gateway core health requires native ComfyUI. Auxiliary provider availability does not redefine core image health.

CORS is disabled by default. Only explicit loopback origins are accepted when local browser CORS is configured; wildcard/non-loopback origins are rejected.

## Verification architecture

`verify-evavo.py` is authoritative. It:

- checks critical files;
- compiles Python sources in memory;
- parses supported PowerShell scripts with the PowerShell AST when available/required;
- validates legacy launcher delegation and rejects retired active behavior;
- automatically discovers root `test-*.py` and root `test_*.py` suites;
- automatically discovers repository-level `tests/test_*.py` provider suites;
- automatically discovers package test suites;
- includes isolated mock/native-ComfyUI simulations;
- includes production-bootstrap, gateway/provider, tunnel, Git-safety, status and unsupported-modality regressions.

The deterministic tests prove contracts without claiming actual GPU/model readiness. The Windows updater/doctor is the machine that performs real native readiness validation.

## Git safety

`safe_main_git.py` is the single Git mutation authority. Historical helpers delegate to it; `safe_git_main.py` is only a compatibility adapter.

The authoritative helper:

- requires branch `main`;
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

Generated images default under `.evavo/outputs/` unless another output directory is configured. Shared task history is lock-protected and atomically written.

Gateway provider task state remains under ignored `.evavo/gateway/` paths.

## Machine-readable capability authority

Current machine-readable descriptions:

```text
.evavo/capabilities.json
EVAVO-CAPABILITIES.json
```

Both preserve image ownership while describing optional governed gateway delegation separately.

The obsolete `evavo-repository-task-manifest.json` was removed because it described retired BeeStation/digest-bound multimodal architecture and nonexistent current tools.

## Current documentation authority

Use these files for current operation and architecture:

- `README.md`
- `CLAUDE.md`
- `AGENT-INTEGRATION.md`
- `AGENT-RECOVERY.md`
- `OPERATIONS-GUIDE.md`
- `GATEWAY-INTEGRATION-GUIDE.md`
- `GATEWAY-AUX-PROVIDERS.md`
- `PROVIDER-INTEGRATION-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
- `DEPLOYMENT-CHECKLIST.md`

Files explicitly labeled historical/superseded are retained only for provenance and must not be used as current setup instructions.
