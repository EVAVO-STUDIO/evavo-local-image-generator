# EVAVO Local Image Generator — Deployment Guide

The current production contract is **native local image generation through ComfyUI**, exposed through CLI/Python/MCP plus an optional loopback HTTP compatibility gateway.

For the deployment checklist, use:

```text
DEPLOYMENT-CHECKLIST.md
```

For active architecture, use:

```text
DEPLOYMENT-ACTIVE.md
```

## Canonical Windows deployment

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

This safely updates `main`, installs dependencies, runs the authoritative full verifier, repairs/provisions native ComfyUI when allowed, validates model/workflow readiness, configures Claude and private MCP, and configures the ChatGPT Secure MCP Tunnel when a valid tunnel ID/runtime key are available.

## Verify

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

## Real image smoke test

```powershell
python evavo.py generate --prompts "EVAVO deployment smoke test" --project deployment_smoke --wait
```

A successful production smoke test must produce a real downloaded image file. The deterministic mock does not count as a renderer.

## Claude

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Claude uses local stdio MCP.

## ChatGPT

Cloud ChatGPT reaches the workstation through OpenAI Secure MCP Tunnel, not by connecting directly to `127.0.0.1`. See `CHATGPT-TUNNEL.md`.

## Optional HTTP gateway

```powershell
.\START-GATEWAY.ps1
python gateway-smoke-test.py
```

The gateway is loopback-only. Image generation is real native ComfyUI; historical video/audio/3D compatibility routes return HTTP `501`.

## Scope

Ollama, Kokoro, BeeStation URI abstraction, digest-bound execution, video, audio, 3D, particle, text, and dedicated PBR-texture generation are **not required components of this repository's verified production image runtime**. Historical compatibility helpers/reports remain only where needed for source/history continuity.

Current authoritative references:

- `README.md`
- `CLAUDE.md`
- `AGENT-INTEGRATION.md`
- `OPERATIONS-GUIDE.md`
- `DEPLOYMENT-CHECKLIST.md`
- `DEPLOYMENT-ACTIVE.md`
- `GATEWAY-INTEGRATION-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
