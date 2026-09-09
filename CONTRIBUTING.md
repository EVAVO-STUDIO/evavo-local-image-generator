# Contributing to EVAVO Local Image Generator

This repository is the native-ComfyUI **image-generation** control plane. Contributions should preserve one truthful production path rather than introducing parallel service graphs or placeholder modality claims.

## Core rules

- Production generation means a real native ComfyUI request and real output evidence.
- The deterministic EVAVO mock is test infrastructure only.
- Do not claim video, audio, 3D, particles, text, or dedicated PBR textures are supported here unless a real implementation, contract and tests are added deliberately.
- Never return fake `queued`/`completed` results for work that was not actually submitted/executed.
- Keep ComfyUI, MCP HTTP and gateway listeners loopback-only unless a separately reviewed secure transport owns exposure.
- Never use blanket `taskkill /IM python.exe`, `.git` deletion/reinitialization, Git identity rewriting, force pushes, or blind lock deletion as recovery logic.
- Preserve existing Claude/ChatGPT/MCP compatibility unless a coordinated version migration is intentional.

## Development setup

```powershell
git clone https://github.com/EVAVO-STUDIO/evavo-local-image-generator.git
cd evavo-local-image-generator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS development can use the normal `source .venv/bin/activate` equivalent for read-only/unit/integration work. Native GPU/Windows-specific behavior still needs workstation validation.

## Authoritative verification

Fast structural/source verification:

```powershell
python evavo.py verify
```

Full suite:

```powershell
python evavo.py verify --full
```

On Windows before a production-facing change is considered ready:

```powershell
python evavo.py verify --full --require-powershell
```

The verifier automatically discovers:

- root `test-*.py` suites;
- root `test_*.py` suites;
- package `evavo_local_image_generator/tests/test_*.py` suites.

Do not maintain a separate hand-written “all tests” list in another script.

## Real backend readiness

Diagnostic check:

```powershell
python evavo.py doctor
```

Production readiness/repair:

```powershell
python agent-doctor.py --repair --provision
```

Production bootstrap:

```powershell
python evavo.py bootstrap
```

`bootstrap` requires native ComfyUI and deliberately passes `--no-mock`.

## Testing guidance

Use isolated native/mock simulators for deterministic tests. Do not require the developer's real port `8188` for ordinary unit/integration suites.

When adding or changing image generation behavior, test as appropriate:

- endpoint/health identity;
- model/checkpoint inventory;
- workflow substitution and live preflight;
- `/prompt` response validation;
- `/history` completion/failure parsing;
- `/view` output collection;
- atomic downloads;
- task-history reconciliation;
- bounded concurrency;
- invalid request handling;
- native-vs-mock production boundaries;
- process identity-safe cleanup.

When touching PowerShell, ensure it parses through the repository verifier's AST check.

## Unsupported modalities

Historical non-image import paths remain for compatibility and raise `UnsupportedGenerationError`/`NotImplementedError`. If you touch them, `evavo_local_image_generator/tests/test_unsupported_modalities.py` must remain green and no compatibility method may fabricate a queue record.

## Gateway changes

The optional HTTP gateway is currently image-only. Preserve:

- loopback-only binding;
- native ComfyUI production health requirement;
- real `/generate/image` execution;
- explicit HTTP `501` for unsupported video/audio/3D routes;
- task/result/WebSocket compatibility for image tasks.

Run:

```powershell
python test-gateway.py
```

and, when validating a live workstation gateway:

```powershell
python gateway-smoke-test.py
```

## MCP changes

Current MCP v2 tools are defined in `evavo_local_image_generator/mcp_server.py`. Claude Desktop uses stdio MCP; the private HTTP transport is Streamable HTTP on loopback.

Keep `COMFYUI_ENDPOINT` canonical. `EVAVO_COMFYUI_ENDPOINT` is a legacy fallback only.

Never introduce arbitrary shell execution through MCP tools. Provisioning/model sources must remain operator-controlled rather than model-invented.

## ChatGPT tunnel changes

The OpenAI Secure MCP Tunnel scripts have an integrity/security contract:

- official release archive digest validation;
- installed executable SHA-256 recording and per-run recheck;
- no plaintext runtime key in repository/state files;
- current-user DPAPI for persisted Windows runtime keys;
- private loopback MCP target;
- no claim that a local doctor alone proves workspace visibility.

Run `test-chatgpt-tunnel.py` and the full verifier after changes.

## Git workflow

Normal development may use branches/pull requests as appropriate, but repository-maintenance shortcuts retained here delegate to `safe_main_git.py`.

For a local reviewed `main` commit/push:

```powershell
python safe_main_git.py --message "describe the actual change"
```

The helper rejects behind/diverged history, generated/runtime state, unexpected remotes and destructive repair behavior; it runs the full verifier by default and never force-pushes.

## Commit messages

Use concise messages that describe the actual change, for example:

```text
feat(mcp): add workflow compatibility inspection
fix(runtime): reject stale managed process identity
test(gateway): cover unsupported modality responses
docs(operations): clarify native renderer requirement
refactor(package): remove legacy storage side effects
```

Do not use a generic “production ready” or “fully autonomous” message unless the commit itself establishes and verifies a precise new contract.

## Pull request / review checklist

Before merging or pushing a substantial change:

- [ ] Current production scope is still truthful.
- [ ] No fake queued/completed outputs were introduced.
- [ ] Relevant unit/integration tests were added or updated.
- [ ] `python evavo.py verify --full` passes.
- [ ] Windows-facing scripts pass PowerShell AST verification on Windows.
- [ ] Native renderer boundaries are preserved.
- [ ] Runtime/generated files are not tracked accidentally.
- [ ] Documentation and `.evavo/capabilities.json` are updated if capabilities changed.
- [ ] Security/authority boundaries were reviewed for new network/process/file behavior.

## Current sources of truth

Use:

- `README.md`
- `PROJECT_SUMMARY.md`
- `CLAUDE.md`
- `AGENT-INTEGRATION.md`
- `OPERATIONS-GUIDE.md`
- `GATEWAY-INTEGRATION-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
- `.evavo/capabilities.json`

Historical/superseded reports are provenance only and must not override current code or runbooks.
