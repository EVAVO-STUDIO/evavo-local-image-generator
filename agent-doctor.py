#!/usr/bin/env python3
"""Diagnose and optionally repair EVAVO agent integration."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import (
    configured_shared_model_roots,
    discover_comfyui,
    ensure_comfyui,
    native_health,
    render_extra_model_paths_yaml,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_ENDPOINT = (os.getenv("EVAVO_COMFYUI_ENDPOINT") or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188").rstrip("/")
DEFAULT_MCP_HOST = os.getenv("EVAVO_MCP_HOST", "127.0.0.1")
DEFAULT_MCP_PORT = int(os.getenv("EVAVO_MCP_PORT", "8765"))


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _claude_config() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"


def _check_claude_config(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"not installed: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid config: {exc}"
    servers = payload.get("mcpServers") if isinstance(payload, dict) else None
    entry = servers.get("evavo-local-image-generator") if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        return False, "EVAVO MCP entry missing"
    return True, f"configured: {path}"


def _output_writable() -> tuple[bool, str]:
    root = Path(os.getenv("EVAVO_GENERATION_OUTPUT_DIR", str(ROOT / ".evavo" / "outputs"))).expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".write-test-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
        return True, str(root)
    except OSError as exc:
        return False, f"{root}: {exc}"


def _agent_tests() -> tuple[bool, str]:
    script = ROOT / "test-agent-integration.py"
    if not script.is_file():
        return False, f"missing {script.name}"
    try:
        result = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "MCP stdio + Streamable HTTP generation/history/image-content tests passed"
    detail = (result.stderr or result.stdout).strip()[-1600:]
    return False, detail or f"exit {result.returncode}"


def _checkpoint_source_configured() -> bool:
    return bool(os.getenv("EVAVO_CHECKPOINT_FILE") or os.getenv("EVAVO_CHECKPOINT_URL"))


def _shared_model_configuration() -> tuple[bool, bool, str]:
    configured = bool(os.getenv("EVAVO_SHARED_MODEL_ROOTS") or os.getenv("EVAVO_COMFYUI_MODEL_ROOTS"))
    if not configured:
        return False, True, "not configured; ComfyUI's own model directories will be used"
    try:
        roots = configured_shared_model_roots()
        rendered = render_extra_model_paths_yaml(roots)
    except RuntimeError as exc:
        return True, False, str(exc)
    blocks = sum(1 for line in rendered.splitlines() if line.startswith("evavo_shared_"))
    return True, True, f"{len(roots)} configured root(s); {blocks} usable ComfyUI model layout(s)"


def _install_app_root(install: Any) -> Path:
    root = Path(install.root)
    return root / "ComfyUI" if getattr(install, "portable", False) else root


def _filesystem_checkpoints(installs: List[Any]) -> List[str]:
    found: List[str] = []
    for install in installs:
        directory = _install_app_root(install) / "models" / "checkpoints"
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth"}:
                found.append(str(path))
    return found


def _provision_comfyui(*, target: Optional[Path] = None, checkpoint_only: bool = False) -> tuple[bool, str]:
    script = ROOT / "provision-comfyui.py"
    if not script.is_file():
        return False, f"missing {script.name}"
    command = [sys.executable, str(script), "--json"]
    if target is not None:
        command.extend(["--target", str(target)])
    if checkpoint_only:
        command.append("--checkpoint-only")
    try:
        result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = None
    if result.returncode == 0 and isinstance(payload, dict) and payload.get("ok"):
        provisioned_target = payload.get("target", "unknown")
        models = payload.get("verification", {}).get("checkpoint_files", []) if isinstance(payload.get("verification"), dict) else []
        return True, f"{payload.get('status', 'provisioned')} {provisioned_target}; local checkpoints={len(models)}"
    detail = str(payload.get("message", "")) if isinstance(payload, dict) else ""
    if not detail:
        detail = (result.stderr or result.stdout).strip()[-2000:]
    return False, detail or f"provisioner exit {result.returncode}"


def _inventory_detail(inventory: Dict[str, Any]) -> str:
    categories = inventory.get("categories")
    if not isinstance(categories, dict):
        return "no category data"
    parts: List[str] = []
    for name, entry in categories.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("available"):
            parts.append(f"{name}={int(entry.get('count', 0))}")
        else:
            parts.append(f"{name}=unavailable")
    return ", ".join(parts) if parts else "no loader categories reported"


def run(repair: bool, provision: bool, endpoint: str, mcp_host: str, mcp_port: int, run_tests: bool) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error", repaired: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail, "repaired": repaired})

    add("python", sys.version_info >= (3, 10), f"{sys.version.split()[0]} at {sys.executable}")

    mcp_spec = importlib.util.find_spec("mcp")
    add("mcp_sdk", mcp_spec is not None, str(mcp_spec.origin) if mcp_spec else 'missing; install mcp[cli]>=2,<3')

    renderer_severity = "error" if repair else "warning"
    shared_configured, shared_ok, shared_detail = _shared_model_configuration()
    add("shared_model_roots", shared_ok, shared_detail, severity=renderer_severity if shared_configured else "info")

    installs = discover_comfyui()
    provision_attempted = False
    if repair and provision:
        missing_runtime = not installs
        configured_model_missing = bool(installs) and _checkpoint_source_configured() and not _filesystem_checkpoints(installs)
        if missing_runtime:
            provision_attempted = True
            provision_ok, provision_detail = _provision_comfyui()
            add("comfyui_provision", provision_ok, provision_detail, severity="error", repaired=provision_ok)
            if provision_ok:
                installs = discover_comfyui()
        elif configured_model_missing:
            provision_attempted = True
            target = Path(installs[0].root)
            provision_ok, provision_detail = _provision_comfyui(target=target, checkpoint_only=True)
            add("checkpoint_provision", provision_ok, provision_detail, severity="error", repaired=provision_ok)

    add(
        "comfyui_install",
        bool(installs),
        "; ".join(str(item.root) for item in installs) if installs else "no local install discovered; use --provision or set EVAVO_COMFYUI_HOME",
        severity=renderer_severity,
        repaired=provision_attempted and bool(installs),
    )

    health = native_health(endpoint)
    repaired_backend = False
    if not health and repair and installs:
        try:
            ensured = ensure_comfyui(endpoint, wait_seconds=180.0, allow_start=True)
            health = ensured.get("health") if isinstance(ensured, dict) else None
            repaired_backend = bool(health)
        except RuntimeError as exc:
            add("backend_repair", False, str(exc), severity="error")
    add(
        "native_comfyui",
        bool(health),
        f"ready at {endpoint}" if health else f"offline at {endpoint}",
        severity=renderer_severity,
        repaired=repaired_backend,
    )

    if health:
        backend = ComfyUIBackend(endpoint)
        try:
            checkpoints = backend.checkpoints()
            checkpoint_detail = f"{len(checkpoints)} available"
            if not checkpoints:
                checkpoint_detail = "none reported"
                if shared_configured:
                    checkpoint_detail += "; shared roots are configured, so restart ComfyUI through EVAVO if it was started externally without the EVAVO extra-model config"
                elif repair and not _checkpoint_source_configured():
                    checkpoint_detail += "; configure EVAVO_CHECKPOINT_FILE, EVAVO_CHECKPOINT_URL, or EVAVO_SHARED_MODEL_ROOTS"
            add("checkpoints", bool(checkpoints), checkpoint_detail, severity="error" if repair else "warning")
        except RuntimeError as exc:
            add("checkpoints", False, str(exc), severity="error" if repair else "warning")

        try:
            inventory = backend.model_inventory(50)
            available = int(inventory.get("available_categories", 0))
            total = int(inventory.get("total_categories", 0))
            add("model_inventory", available > 0, f"loader categories {available}/{total}; {_inventory_detail(inventory)}", severity="info" if available > 0 else "warning")
        except RuntimeError as exc:
            add("model_inventory", False, str(exc), severity="warning")
    else:
        add("checkpoints", False, "not checked because native ComfyUI is offline", severity=renderer_severity)
        add("model_inventory", False, "not checked because native ComfyUI is offline", severity="warning")

    writable, output_detail = _output_writable()
    add("output_directory", writable, output_detail)

    claude_ok, claude_detail = _check_claude_config(_claude_config())
    add("claude_stdio", claude_ok, claude_detail, severity="warning")

    http_ok = _port_open(mcp_host, mcp_port)
    add(
        "mcp_http",
        http_ok,
        f"listening on http://{mcp_host}:{mcp_port}/mcp" if http_ok else f"not listening on {mcp_host}:{mcp_port}; run START-AGENT-MCP.ps1 or install autostart",
        severity="warning",
    )

    startup = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "EVAVO-Agent-MCP.cmd"
    add("mcp_http_autostart", startup.is_file(), str(startup) if startup.is_file() else "not installed", severity="warning")

    if run_tests and mcp_spec is not None:
        tests_ok, tests_detail = _agent_tests()
        add("agent_protocol_tests", tests_ok, tests_detail)

    hard_failures = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["ok"] and item["severity"] == "warning"]
    return {
        "ok": not hard_failures,
        "status": "operational" if not hard_failures and not warnings else ("degraded" if not hard_failures else "needs_attention"),
        "repair_requested": repair,
        "provision_requested": provision,
        "endpoint": endpoint,
        "mcp_http": f"http://{mcp_host}:{mcp_port}/mcp",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO Claude/ChatGPT agent integration doctor")
    parser.add_argument("--repair", action="store_true", help="Start native ComfyUI and require real-renderer/checkpoint readiness")
    parser.add_argument("--provision", action="store_true", help="When repairing, provision missing official ComfyUI and any explicitly configured checkpoint source")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--mcp-host", default=DEFAULT_MCP_HOST)
    parser.add_argument("--mcp-port", type=int, default=DEFAULT_MCP_PORT)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.mcp_port <= 65535:
        parser.error("--mcp-port must be between 1 and 65535")
    if args.provision and not args.repair:
        parser.error("--provision requires --repair")
    payload = run(args.repair, args.provision, args.endpoint.rstrip("/"), args.mcp_host, args.mcp_port, not args.skip_tests)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("EVAVO Agent Doctor")
        print("=" * 78)
        for check in payload["checks"]:
            marker = "OK" if check["ok"] else ("WARN" if check["severity"] == "warning" else "FAIL")
            repaired = " [repaired]" if check.get("repaired") else ""
            print(f"[{marker:<4}] {check['name']:<22} {check['detail']}{repaired}")
        print("=" * 78)
        print(payload["status"])
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
