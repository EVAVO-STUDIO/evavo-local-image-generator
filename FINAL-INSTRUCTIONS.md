# EVAVO Local Image Generator — Current Final Instructions

The old "99% complete / just commit these files" milestone is finished and superseded. The repository is already being maintained directly on `main`; the remaining proof of readiness belongs on the actual Windows workstation/GPU.

## Canonical workstation command

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

That command is the supported end-to-end setup/verification path. It does **not** blindly overwrite a dirty worktree.

## What it verifies

- current Python sources compile;
- supported PowerShell scripts parse before configuration writes;
- modern root/package test suites pass;
- retained legacy launchers delegate safely and do not revive blanket process kills, hidden service graphs, fake multimodal outputs, or destructive source regenerators;
- native ComfyUI can be discovered/repaired/provisioned when allowed;
- the active workflow/model contract is ready;
- Claude stdio MCP/private HTTP MCP are configured;
- final backend status is healthy;
- ChatGPT Secure MCP Tunnel is configured/started when its OpenAI tunnel ID/runtime key are already available.

## Real image proof

```powershell
python evavo.py generate --prompts "EVAVO final real-render smoke test" --project final_smoke --wait
```

A real production proof is a `completed` task with an actual non-empty downloaded image path. A deterministic mock queue response is not sufficient.

## Claude

Restart Claude Desktop after the updater changes its MCP configuration. Claude uses local stdio MCP.

## ChatGPT

ChatGPT uses OpenAI Secure MCP Tunnel to reach the private workstation MCP listener. See `CHATGPT-TUNNEL.md`. A passing local tunnel doctor proves local profile/integrity/process readiness, not by itself workspace visibility in ChatGPT.

## No manual commit script required

Do not use old `COMMIT-UPGRADE.ps1`, `PUSH-UPGRADE-TO-MAIN.ps1`, or milestone instructions as the primary workflow. Current repository changes are committed directly to `main`; workstation deployment should focus on pulling/verifying the exact head.

## Current scope

This repository verifies native **image generation**. Historical claims of automatic video/audio/3D/particle/text/PBR generation in this repo are superseded.

Current source-of-truth docs:

- `README.md`
- `CLAUDE.md`
- `AGENT-INTEGRATION.md`
- `AUTOMATION-GUIDE.md`
- `OPERATIONS-GUIDE.md`
- `DEPLOYMENT-CHECKLIST.md`
- `GATEWAY-INTEGRATION-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
