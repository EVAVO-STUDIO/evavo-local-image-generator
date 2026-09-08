# EVAVO Agent Integration

EVAVO exposes the same native ComfyUI generation pipeline to Claude, ChatGPT-compatible MCP clients, Codex/IDE agents, and direct Python automation.

## Automation contract

An agent does **not** need to know how ComfyUI was installed or manually start services first.

On a generation call EVAVO can:

1. check `http://127.0.0.1:8188` for a real native ComfyUI;
2. discover a local ComfyUI source or Windows portable install;
3. start it in the background when it is installed but offline;
4. wait for `/system_stats` readiness;
5. discover checkpoints from `CheckpointLoaderSimple`;
6. queue `/prompt` with a standard or custom API workflow;
7. poll `/history/<prompt_id>`;
8. download `/view` outputs atomically;
9. return concrete local file paths to the calling agent.

The deterministic EVAVO mock is never accepted as a native renderer by the agent lifecycle manager.

## ComfyUI discovery

Automatic discovery checks common Windows locations including:

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

For a non-standard installation set:

```powershell
$env:EVAVO_COMFYUI_HOME = "D:\AI\ComfyUI"
```

Multiple additional search roots can be supplied with `EVAVO_COMFYUI_SEARCH_PATHS` using the platform path separator.

## Claude: stdio MCP

Claude/desktop/IDE clients can spawn the server directly:

```text
command: python
args: -m evavo_local_image_generator.mcp_server
```

The repository `.mcp.json` contains this profile.

No MCP listening port is required for stdio operation.

## ChatGPT/local MCP clients: Streamable HTTP

Start the loopback MCP endpoint:

```powershell
.\START-AGENT-MCP.ps1
```

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

Equivalent Python command:

```powershell
python -m evavo_local_image_generator.mcp_server `
  --transport streamable-http `
  --host 127.0.0.1 `
  --port 8765 `
  --path /mcp
```

The launcher intentionally binds only to loopback. A cloud-hosted client cannot reach workstation localhost unless the product provides a local bridge/connector. Do not expose this service to the public internet merely to make it reachable; use an authenticated connector/tunnel architecture if remote access is deliberately required.

## Agent tools

The MCP server exposes:

- `ensure_backend` — verify or auto-start native ComfyUI;
- `health_check` — backend version/device health;
- `discover_backends` — local ComfyUI installations EVAVO can launch;
- `list_checkpoints` — installed checkpoints;
- `generate_image` — queue and optionally wait/download;
- `generation_status` — inspect a prompt ID;
- `collect_generation` — wait/download an existing prompt;
- `stop_managed_backend` — stop only native ComfyUI started by EVAVO.

`generate_image` defaults to `auto_start=true` and `wait=true`, making it suitable for a one-call agent workflow.

## Default generated files

Agent downloads default to:

```text
<repo>\.evavo\outputs\<project>\
```

Override globally:

```powershell
$env:EVAVO_GENERATION_OUTPUT_DIR = "D:\EVAVO\generated"
```

or pass `output_dir` to the tool.

## Custom ComfyUI API workflow

For Flux, SDXL variants, custom nodes, ControlNet or other pipelines export API-format JSON from ComfyUI and set:

```powershell
$env:EVAVO_COMFYUI_WORKFLOW = "C:\workflows\production-api.json"
```

The workflow loader supports placeholders inside string values:

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

## Validation

Full workstation update and validation:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

This runs both:

```powershell
python test-agent-integration.py
python evavo.py bootstrap --skip-pull
```

Agent transport tests verify:

- MCP package import/server registration;
- ComfyUI installation discovery;
- stdio MCP process startup;
- loopback Streamable HTTP MCP startup.

Operational tests separately verify mock/native health, native workflow submission, output history and file downloads, batch tracking, offline behavior and controller lifecycle.

## Safety/lifecycle rules

- Native and MCP HTTP listeners are loopback by default.
- EVAVO never uses broad `taskkill /IM python.exe` cleanup.
- `stop_managed_backend` stops only a PID recorded as started by EVAVO.
- An already-running user-managed ComfyUI is reused and is not stopped by EVAVO.
- If an EVAVO-managed mock is occupying port 8188 and a native install is available, EVAVO may stop only that recorded mock PID before starting native ComfyUI.
- Output downloads use temporary files followed by atomic replacement.
