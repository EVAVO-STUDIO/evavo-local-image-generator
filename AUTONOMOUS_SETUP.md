# EVAVO Autonomous Image Setup

This repository supports automated **native ComfyUI image generation** for CLI, Claude Desktop and ChatGPT. Historical video-generation and hardcoded `C:\AI\ComfyUI` instructions are retired.

## Canonical Windows setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater verifies the repository before changing agent configuration, provisions/repairs ComfyUI when allowed, validates the active image workflow/model contract, installs Claude stdio MCP, installs the private loopback MCP listener, and configures the ChatGPT tunnel when OpenAI tunnel credentials are already available.

## Direct readiness repair

```powershell
python agent-doctor.py --repair --provision
```

This strict gate requires a real native renderer and the model assets required by the active workflow. The deterministic mock does not count as ready.

## Direct image generation

```powershell
python evavo.py generate --prompts "landscape at sunset" --project demo --wait
```

Batch:

```powershell
python evavo.py generate --prompts "scene one" "scene two" "scene three" --project game_assets --wait
```

## Claude Desktop

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses local stdio MCP. Restart Claude Desktop after changing its MCP configuration.

## ChatGPT

ChatGPT uses OpenAI Secure MCP Tunnel to reach the private workstation MCP endpoint. See `CHATGPT-TUNNEL.md`.

## Backward-compatible Python API

Older code may still use:

```python
from claude_control import ClaudeController

controller = ClaudeController()
result = controller.generate_image_simple("landscape at sunset", quality="high")
```

That compatibility API now performs real native-ComfyUI image generation. Its historical video method deliberately returns `NOT_IMPLEMENTED` instead of fabricating a completed MP4.

## Historical launchers

`run_autonomous.py`, `demo_autonomous.py`, `RUN-GENERATION.py`, `RUN-FULL-GENERATION.py`, `LAUNCH-GENERATION.py`, `EXECUTE-GENERATION.py` and related batch/PowerShell shortcuts now delegate to the same canonical image runtime. They do not start unrelated services, write fake output files, copy to hardcoded storage, or generate without explicit intent.

## Verification

```powershell
python evavo.py verify --full --require-powershell
python evavo.py status
```

For deeper details see:

- `README.md`
- `AGENT-INTEGRATION.md`
- `OPERATIONS-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
