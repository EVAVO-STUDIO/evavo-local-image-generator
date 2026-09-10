# ChatGPT Secure MCP Tunnel for EVAVO

This is the supported bridge between ChatGPT and EVAVO's private workstation MCP server.

Claude Desktop can spawn EVAVO locally through stdio. ChatGPT is cloud-hosted and cannot directly connect to `127.0.0.1` on the workstation. For ChatGPT, EVAVO therefore uses OpenAI Secure MCP Tunnel: the official `tunnel-client` runs on Windows, opens an outbound connection to OpenAI, and forwards tunnel traffic to the private EVAVO MCP endpoint.

ComfyUI remains private on `127.0.0.1:8188`. EVAVO MCP remains private on `127.0.0.1:8765/mcp`. Neither service needs an inbound firewall rule or public internet listener.

## One-time OpenAI prerequisite

A tunnel ID and a tunnel runtime API key come from OpenAI Platform/workspace administration and cannot be fabricated by this repository.

Current tunnel IDs use this format:

```text
tunnel_<32 lowercase hexadecimal characters>
```

The runtime API key used by `tunnel-client run` must have the appropriate tunnel permissions for the target tunnel/workspace (normally Tunnels Read + Use). Tunnel creation itself is an administrative Platform action; EVAVO deliberately does not ask for or persist an OpenAI Admin API key just to automate that one-time step.

Once an administrator has created/associated the tunnel, set the ID for the setup shell:

```powershell
$env:EVAVO_OPENAI_TUNNEL_ID = "tunnel_0123456789abcdef0123456789abcdef"
```

Set the runtime key only in the current process when possible:

```powershell
$env:CONTROL_PLANE_API_KEY = "<runtime tunnel API key>"
```

Do not commit either credential to the repository.

## Fully configure the workstation side

With the tunnel ID and runtime key available in the current PowerShell process:

```powershell
.\INSTALL-CHATGPT-MCP-TUNNEL.ps1 -PersistRuntimeKey
.\INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
```

The first command:

1. resolves the latest public `openai/tunnel-client` release;
2. selects the Windows package for the machine architecture;
3. requires the release asset to publish a SHA-256 digest;
4. downloads the package from the official OpenAI GitHub release;
5. verifies the downloaded ZIP against the published digest before extraction;
6. installs `tunnel-client.exe` under `.evavo/tools/`;
7. calculates and records the SHA-256 of the executable extracted from that verified archive;
8. rechecks that recorded executable digest whenever an existing installation is reused;
9. ensures the private EVAVO MCP listener is configured;
10. initializes an `evavo-chatgpt` profile using the HTTP/DCR sample contract;
11. binds the profile to the supplied tunnel ID and `http://127.0.0.1:8765/mcp` private target;
12. writes only non-secret profile metadata under `.evavo/chatgpt-tunnel.json`;
13. stores the runtime key with Windows DPAPI when `-PersistRuntimeKey` is explicitly requested;
14. runs `tunnel-client doctor --profile evavo-chatgpt --explain` when a runtime key is available.

The second command installs a lightweight current-user Windows Startup launcher and starts the tunnel now. Login autostart **requires** the DPAPI-encrypted key store; an ephemeral process environment variable is intentionally not treated as reboot-persistent.

## Secure runtime-key storage

Store the key interactively:

```powershell
.\SAVE-CHATGPT-TUNNEL-KEY.ps1
```

or, when `CONTROL_PLANE_API_KEY` is already set in the current shell:

```powershell
.\SAVE-CHATGPT-TUNNEL-KEY.ps1 -FromEnvironment
```

The encrypted blob is stored outside the repository at:

```text
%LOCALAPPDATA%\EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi
```

It is encrypted for the current Windows user through DPAPI. The plaintext key is not written to `.evavo`, Claude configuration or Windows Startup.

Remove it with:

```powershell
.\SAVE-CHATGPT-TUNNEL-KEY.ps1 -Remove
```

## Start manually

Foreground/manual diagnostics:

```powershell
.\START-CHATGPT-MCP-TUNNEL.ps1
```

Skip the local tunnel-client preflight only when it has already passed and a lightweight launch is intended:

```powershell
.\START-CHATGPT-MCP-TUNNEL.ps1 -SkipDoctor
```

The script:

- loads the configured profile from `.evavo/chatgpt-tunnel.json`;
- verifies `tunnel-client.exe` still matches the executable SHA-256 recorded immediately after extraction from the verified official archive;
- refuses to run when executable integrity metadata is missing/invalid or the hash differs;
- obtains `CONTROL_PLANE_API_KEY` from the current process or decrypts the DPAPI blob only after the executable integrity check passes;
- verifies the private EVAVO MCP port is either free or owned by the EVAVO MCP server;
- starts EVAVO MCP privately when required;
- runs `tunnel-client doctor` unless skipped;
- runs `tunnel-client run --profile <profile>` in the foreground;
- clears a DPAPI-loaded runtime key from the PowerShell environment when the runtime exits.

Because the login autostart calls this same launcher, the executable hash is also rechecked on every Windows-login tunnel start.

## Diagnose

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1
```

Require a usable runtime key and a running tunnel process:

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning
```

Machine-readable output:

```powershell
.\CHATGPT-TUNNEL-DOCTOR.ps1 -RequireRuntimeKey -RequireRunning -Json
```

The doctor checks separately:

- non-secret EVAVO tunnel state;
- tunnel ID format;
- profile name;
- tunnel-client file presence;
- tunnel-client executable SHA-256 against verified-install metadata;
- hash-verified executable smoke execution;
- private localhost MCP target;
- actual local MCP listener ownership;
- runtime-key availability without printing it;
- `tunnel-client doctor` local preflight;
- whether the named `tunnel-client run` process is active.

Important: `tunnel-client doctor` is a **local preflight**. Passing it does not by itself prove that a ChatGPT workspace app is visible or that the long-lived runtime has successfully polled work. A running daemon plus the ChatGPT/Platform connector configuration completes that system.

## ChatGPT-side app connection

After the workstation tunnel runtime is configured and running, complete the OpenAI-side connection in the eligible ChatGPT workspace:

1. enable Developer mode for Plugins/apps if required by the workspace;
2. create or edit the EVAVO app/plugin connection;
3. choose **Tunnel** as the connection type;
4. select or paste the same tunnel ID used by the workstation profile;
5. connect/save the app;
6. verify the EVAVO MCP tools appear, including `open_comfyui_ui`, `health_check`, `model_inventory`, `generate_image`, `generate_batch`, `read_output_image`, `task_history` and `task_statistics`.

Once connected, `open_comfyui_ui` starts or reuses native ComfyUI, waits for
verified readiness, and asks the signed-in Windows session to open the local UI
in its default browser. Browser presentation stays local; the tunnel does not
publish port 8188.

Workspace administrators may need to create, publish or allow the app depending on organization policy.

## Canonical updater integration

The normal workstation updater also knows about ChatGPT tunneling:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

If `EVAVO_OPENAI_TUNNEL_ID` is present, or an existing `.evavo/chatgpt-tunnel.json` already supplies a tunnel ID, the updater configures the verified tunnel profile automatically.

If `CONTROL_PLANE_API_KEY` is present only in the setup shell, the updater can start the tunnel for the current session without persisting the key.

For persistent login startup, explicitly opt into DPAPI storage before/during setup:

```powershell
$env:EVAVO_PERSIST_OPENAI_TUNNEL_KEY = "1"
.\UPDATE-AND-VERIFY-EVAVO.ps1
```

This persistence opt-in is acted on only when `CONTROL_PLANE_API_KEY` is present. The key is stored using DPAPI, not in the updater or Startup command.

Skip all ChatGPT tunnel configuration when deliberately working only on Claude/local MCP:

```powershell
.\UPDATE-AND-VERIFY-EVAVO.ps1 -SkipChatGPTTunnel
```

If no tunnel ID exists, the updater does not fail the rest of EVAVO/Claude setup. It reports the OpenAI Platform tunnel as the remaining external prerequisite.

## Security boundaries

- Do not expose ComfyUI directly to the internet.
- Do not bind EVAVO MCP to `0.0.0.0`; it remains loopback-only.
- The OpenAI tunnel is the external bridge and originates outbound from the workstation.
- The tunnel-client archive is SHA-256 verified against the official GitHub release asset digest before installation.
- The executable extracted from that verified archive is separately SHA-256 fingerprinted and checked before every tunnel run.
- `CONTROL_PLANE_API_KEY` is never stored in repository state.
- Windows login autostart requires a current-user DPAPI blob and contains no plaintext key.
- `EVAVO_CHECKPOINT_URL` is also not persisted by EVAVO agent installers because signed model URLs can contain credentials.
- MCP `provision_backend` takes no repository/model URL arguments from the model; provisioning sources come from operator-controlled environment only.
- MCP `read_output_image` is restricted to authorized generated image files and cannot read arbitrary workstation files.
- EVAVO validates managed process identity before terminating ComfyUI or its deterministic mock.

## Files

Repository scripts:

```text
INSTALL-CHATGPT-MCP-TUNNEL.ps1
SAVE-CHATGPT-TUNNEL-KEY.ps1
START-CHATGPT-MCP-TUNNEL.ps1
INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1
CHATGPT-TUNNEL-DOCTOR.ps1
test-chatgpt-tunnel.py
```

Generated/non-secret repository-local state (ignored by Git):

```text
.evavo\chatgpt-tunnel.json
.evavo\tools\tunnel-client.exe
.evavo\tools\tunnel-client-install.json
```

`tunnel-client-install.json` records release metadata plus the SHA-256 of the extracted executable. It contains no runtime API key.

Secret Windows-user state (outside the repo):

```text
%LOCALAPPDATA%\EVAVO\Secure\chatgpt-tunnel-runtime-key.dpapi
```

Windows login launcher:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EVAVO-ChatGPT-MCP-Tunnel.cmd
```
