# EVAVO Local Image Generator agent rules

This repository is the canonical EVAVO control plane for **native ComfyUI image generation**. These rules apply to ChatGPT, Codex, Claude, local MCP clients and other coding/automation agents.

Read `AGENT-INTEGRATION.md` and `COMFYUI-STARTUP-DIAGNOSTICS.md` before changing backend lifecycle or recovery behavior.

## One capability contract for every agent

Claude and ChatGPT must use the same MCP semantics. Transport differs; capability behavior does not.

- Claude Desktop: local stdio MCP via `INSTALL-CLAUDE-MCP.ps1`.
- ChatGPT: the same private MCP server through the OpenAI Secure MCP Tunnel described in `CHATGPT-TUNNEL.md`.
- Coding agents with workstation execution: prefer EVAVO Local Compute for bounded PowerShell/Python/Git work when MCP itself cannot perform the required local operation.

Do not create separate Claude-only or ChatGPT-only repair logic when the shared MCP/library path can own it.

## Canonical ComfyUI startup/recovery sequence

For a backend that will not start:

1. `last_startup_failure`
2. `diagnose_backend(seconds=60, cpu=true)`
3. If and only if the structured category is `missing_dependency`, call `repair_backend_dependencies()`.
4. Re-run `diagnose_backend(seconds=60, cpu=true)`.
5. Call `ensure_backend`.
6. Run a real generation and require verified image output before declaring the renderer healthy.

If the category is `custom_node_dependency`, do **not** mutate core ComfyUI requirements. Isolate with `diagnose_backend(..., disable_all_custom_nodes=true)` and repair the specific reviewed custom node separately.

`repair_backend_dependencies` is deliberately constrained:

- no arbitrary package name;
- no arbitrary Python path;
- no arbitrary ComfyUI path through MCP;
- normal mutation requires structured `missing_dependency` evidence;
- uses the discovered checkout's own `requirements.txt` and selected ComfyUI interpreter;
- never invokes a shell;
- never starts, stops or broadly kills Python/ComfyUI processes;
- returns a structured receipt.

`force_sync=true` is an explicit operator/agent override, not the normal recovery path.

## Process safety

Never use blanket process cleanup such as:

```text
taskkill /IM python.exe /F
Stop-Process -Name python
```

Only terminate a process when EVAVO has identity proof that it owns that exact process tree. Never kill a user-managed ComfyUI instance.

A `.lock` filename by itself is not proof of a live owner. Follow the repository's named-mutex/process-identity contracts.

## Generation proof

A healthy HTTP port is not enough. Completion requires a real ComfyUI prompt that reaches a terminal successful history/job state and produces an image whose bytes pass EVAVO output validation.

Do not describe queued work as completed. Do not describe a spawned process as a healthy renderer without the runtime receipt.

## Workstation execution fallback

When an agent needs local PowerShell, Python, Git, build/test or filesystem execution that is not exposed by this MCP server, use the EVAVO Local Compute workstation bridge/operator contract in `EVAVO-STUDIO/evavo-local-compute`.

- prefer non-interactive structured execution;
- capture exit code, stdout/stderr and postconditions;
- use the operator profile only for network/Git mutation;
- never tell the user to double-click a script when the connected workstation execution authority can run it;
- if no workstation authority is actually connected, state that limitation instead of claiming the command ran.

Desktop Commander / Remote Desktop Commander is excluded from this workflow.

## Git safety

Preserve unrelated local progress and moving-main history.

- work on `main` unless the task explicitly requires otherwise;
- fetch before mutation when operating a workstation checkout;
- fast-forward only when safe;
- stage intended paths only;
- commit descriptive changes and push `origin main`;
- verify the remote commit;
- never `reset --hard`, `clean -fd`, blind-stash, destructive rebase or force-push to bypass divergence or dirty state.

## Current shared MCP recovery tools

```text
ensure_backend
diagnose_backend
last_startup_failure
repair_backend_dependencies
health_check
discover_backends
```

The full tool surface is documented in `AGENT-INTEGRATION.md`. The deterministic mock is test infrastructure only and must never be accepted as the production renderer.
