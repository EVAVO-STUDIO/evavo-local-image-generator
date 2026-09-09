# EVAVO Agent Recovery

Use this runbook when native image generation, Claude MCP, the private HTTP MCP listener, or the ChatGPT Secure MCP Tunnel appears stuck.

Do **not** kill all Python processes, delete `.git` locks, recreate the repository, expose local ports publicly, or regenerate source files from historical templates.

## 1. Verify repository integrity

```powershell
cd C:\Gitrepos\evavo-local-image-generator
python evavo.py verify --full --require-powershell
```

If the local checkout is intentionally clean and simply stale:

```powershell
git pull --ff-only origin main
python evavo.py verify --full --require-powershell
```

## 2. Repair the real image runtime

```powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

This discovers/reuses/provisions native ComfyUI according to owner configuration and requires the active workflow/model contract to be real-render capable. The deterministic EVAVO mock is not accepted by this strict gate.

## 3. Test a real image

```powershell
python evavo.py generate --prompts "EVAVO recovery smoke test" --project recovery_smoke --wait
```

A successful proof includes a completed task and a real non-empty downloaded image file.

## 4. Private HTTP MCP recovery

Stop only the verified EVAVO Streamable HTTP listener:

```powershell
.\STOP-AGENT-MCP.ps1
```

Start it again:

```powershell
.\START-AGENT-MCP.ps1
```

Remove/reinstall its current-user login autostart when needed:

```powershell
.\STOP-AGENT-MCP.ps1 -RemoveAutostart
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
```

The stop helper refuses to terminate a different process merely because it occupies the same port.

## 5. Claude recovery

Reinstall/merge the current stdio MCP profile:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop afterward. The installer preserves other MCP server entries.

## 6. ChatGPT tunnel recovery

Diagnose without exposing the runtime key:

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

Stop only the configured, executable-path-verified tunnel profile:

```powershell
.\STOP-CHATGPT-MCP-TUNNEL.ps1
```

Start manually for foreground diagnostics:

```powershell
.\START-CHATGPT-MCP-TUNNEL.ps1
```

Remove/reinstall persistent login startup:

```powershell
.\STOP-CHATGPT-MCP-TUNNEL.ps1 -RemoveAutostart
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

The tunnel launcher verifies the installed `tunnel-client.exe` SHA-256 before use and preserves a caller-supplied `CONTROL_PLANE_API_KEY`; only a temporary DPAPI-decrypted copy is cleared by the launcher.

A passing tunnel doctor is a **local preflight/process check**. It does not by itself prove ChatGPT workspace visibility; that also depends on the OpenAI workspace/tunnel association.

## 7. Optional HTTP gateway recovery

```powershell
python EVAVO-SERVICE-MANAGER.py stop
.\START-GATEWAY.ps1
python gateway-smoke-test.py
```

The gateway is loopback-only and production-image-only. Historical video/audio/3D routes intentionally return HTTP `501`.

## 8. Full workstation convergence

When individual recovery is not needed and the worktree is clean:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

This is the canonical convergence path for dependencies, verifier suites, native renderer readiness, Claude/private MCP configuration, and conditional ChatGPT tunnel setup.

## Machine-readable capability contract

Agents/orchestrators can inspect:

```text
EVAVO-CAPABILITIES.json
```

That manifest is synchronized against the registered MCP tools by `test-capability-manifest.py`.
