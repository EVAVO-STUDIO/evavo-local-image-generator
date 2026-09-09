# EVAVO Local Image Generator - Deployment Checklist

The verified production contract of this repository is **native local image generation through ComfyUI**, exposed consistently through CLI, Python, Claude MCP and ChatGPT Secure MCP Tunnel.

## Windows deployment

### 1. Update and verify

```powershell
cd C:\Gitrepos\evavo-local-image-generator
git pull --ff-only origin main
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

The updater is the canonical deployment path. It installs the root `requirements.txt`, executes the authoritative verifier and all discovered modern test suites, repairs/provisions native ComfyUI when allowed, validates the active model/workflow contract, installs agent integrations, and reports final status.

### 2. Confirm real renderer readiness

```powershell
python agent-doctor.py --repair --provision
python evavo.py status
```

For the built-in txt2img workflow, at least one usable checkpoint is required. A configured custom workflow may require different loader assets; `workflow_preflight`/the agent doctor validate that contract. The deterministic EVAVO mock is not a production renderer.

### 3. Smoke-test a real image

```powershell
python evavo.py generate --prompts "EVAVO deployment smoke test" --project deployment_smoke --wait
```

Confirm that the result is completed and a real output file exists under `.evavo\outputs\` or the configured generation output directory.

### 4. Claude Desktop

```powershell
.\INSTALL-CLAUDE-MCP.ps1
```

Restart Claude Desktop after the MCP configuration changes. Claude uses local stdio MCP.

### 5. ChatGPT

ChatGPT does not connect directly to workstation localhost. Use the OpenAI Secure MCP Tunnel documented in `CHATGPT-TUNNEL.md`.

Once a valid tunnel ID/runtime key are available:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_<32 lowercase hex characters>"
$env:CONTROL_PLANE_API_KEY = "<runtime key>"
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

The tunnel client is downloaded from the official `openai/tunnel-client` release, the release ZIP SHA-256 is verified, the extracted executable digest is recorded, and every launch verifies that executable digest before running it.

## Verified feature checklist

- [x] native ComfyUI health/detection
- [x] source + Windows-portable ComfyUI discovery
- [x] constrained runtime/checkpoint provisioning
- [x] shared external model roots
- [x] model inventory and custom-workflow preflight
- [x] real `/prompt` submission
- [x] `/history/<prompt_id>` completion tracking
- [x] `/view` output download
- [x] bounded concurrent image batches
- [x] durable shared CLI/MCP task history
- [x] MCP v2 stdio + loopback Streamable HTTP
- [x] native MCP image-content return
- [x] Claude Desktop installer
- [x] outbound OpenAI Secure MCP Tunnel tooling
- [x] loopback-only optional HTTP compatibility gateway
- [x] authoritative repository verifier
- [x] identity-safe managed-process stop behavior

## Explicitly not claimed here

Video, audio, 3D model, particle, text, and dedicated PBR-texture generation are not part of this repository's verified production runtime. Historical routes/wrappers now fail explicitly or delegate to the image-only control plane rather than fabricating completed work.

## Operational references

- `README.md`
- `AGENT-INTEGRATION.md`
- `OPERATIONS-GUIDE.md`
- `CHATGPT-TUNNEL.md`
- `QUICK-REFERENCE.md`
- `GATEWAY-INTEGRATION-GUIDE.md` for the optional HTTP compatibility gateway
