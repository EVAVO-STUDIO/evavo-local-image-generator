# EVAVO Autonomous Image Automation

EVAVO can operate autonomously for **native local image generation**, but autonomy now means a safe agent-owned lifecycle—not hidden sample jobs, blanket process killing, or unrequested Scheduled Tasks.

## What EVAVO automates

For a Claude/ChatGPT image request EVAVO can:

1. inspect the configured native ComfyUI endpoint;
2. discover source or Windows-portable ComfyUI installations;
3. provision the official source runtime when enabled and missing;
4. reuse configured shared model roots;
5. repair an explicitly configured checkpoint source when needed;
6. start native ComfyUI without a visible console;
7. verify readiness and model/workflow compatibility;
8. submit the ComfyUI API workflow;
9. wait for history/output completion;
10. download output files atomically;
11. persist task status/metadata;
12. return file paths or native MCP image content.

The deterministic EVAVO mock is for isolated tests only and is not accepted as a real renderer by strict agent readiness.

## One-command workstation setup

```powershell
cd C:\Gitrepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

That is the preferred replacement for historical `MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Full` behavior.

## Claude

Claude Desktop uses stdio MCP and can spawn the EVAVO server as needed:

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

The canonical updater installs this automatically.

## ChatGPT

ChatGPT uses the outbound OpenAI Secure MCP Tunnel; it does not connect directly to workstation `127.0.0.1`.

See `CHATGPT-TUNNEL.md`.

## Login automation

EVAVO supports **current-user login autostart only for the private MCP listener and, when securely configured, the ChatGPT tunnel**:

```powershell
.\INSTALL-AGENT-MCP-AUTOSTART.ps1
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

The ChatGPT tunnel autostart requires the runtime key to be stored with Windows current-user DPAPI. The plaintext key is never embedded in the Startup command.

EVAVO does **not** silently create arbitrary Windows Scheduled Tasks for image generation.

## Generation is request-driven

Explicit CLI example:

```powershell
python evavo.py generate --prompts "your prompt" --project demo --wait
```

Historical launchers no longer generate sample assets just because they were started. They either prepare/verify the backend or require explicit prompts/`--examples`.

## Monitoring

```powershell
python monitor-evavo.py --interval 30
```

or the compatibility monitor mode:

```powershell
.\MASTER-AUTOMATION-CONTROLLER.ps1 -Mode Monitor -HealthCheckInterval 30
```

The compatibility controller delegates to the canonical native lifecycle. It no longer creates Scheduled Tasks or kills arbitrary Python processes.

## Verification

```powershell
python evavo.py verify --full --require-powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

The full verifier automatically discovers modern root/package test suites and checks retained compatibility launchers for dangerous retired behavior.

## Process safety

- no `taskkill /IM python.exe` cleanup;
- no persistent `cmd /k` or PowerShell `-NoExit` service windows;
- only identity-verified EVAVO-managed native/mock processes may be stopped;
- user-managed ComfyUI is reused and never killed;
- unsupported video/audio/3D routes fail explicitly instead of reporting fake success.

## Current scope

This repository is the **image-generation control plane**. Video, audio, 3D, particle, text and dedicated PBR-texture systems belong in their dedicated EVAVO tooling and are not advertised here as generated/completed work.

For complete current instructions use `AGENT-INTEGRATION.md`, `OPERATIONS-GUIDE.md`, `CHATGPT-TUNNEL.md`, and `QUICK-REFERENCE.md`.
