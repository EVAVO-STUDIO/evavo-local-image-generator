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
from typing import Any, Dict, List

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.comfyui_runtime import discover_comfyui, ensure_comfyui, native_health

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
        result = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "MCP stdio + Streamable HTTP negotiation passed"
    detail = (result.stderr or result.stdout).strip()[-1200:]
    return False, detail or f"exit {result.returncode}"


def run(repair: bool, endpoint: str, mcp_host: str, mcp_port: int, run_tests: bool) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error", repaired: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail, "repaired": repaired})

    add("python", sys.version_info >= (3, 10), f"{sys.version.split()[0]} at {sys.executable}")

    mcp_spec = importlib.util.find_spec("mcp")
    add("mcp_sdk", mcp_spec is not None, str(mcp_spec.origin) if mcp_spec else 'missing; install mcp[cli]>=2,<3')

    installs = discover_comfyui()
    add(
        "comfyui_install",
        bool(installs),
        "; ".join(str(item.root) for item in installs) if installs else "no local install discovered; set EVAVO_COMFYUI_HOME",
        severity="warning",
    )

    health = native_health(endpoint)
    repaired_backend = False
    if not health and repair:
        try:
            ensured = ensure_comfyui(endpoint, wait_seconds=120.0, allow_start=True)
            health = ensured.get("health") if isinstance(ensured, dict) else None
            repaired_backend = bool(health)
        except RuntimeError as exc:
            add("backend_repair", False, str(exc), severity="warning")
    add(
        "native_comfyui",
        bool(health),
        f"ready at {endpoint}" if health else f"offline at {endpoint}",
        severity="warning",
        repaired=repaired_backend,
    )

    if health:
        try:
            checkpoints = ComfyUIBackend(endpoint).checkpoints()
            add("checkpoints", bool(checkpoints), f"{len(checkpoints)} available" if checkpoints else "none reported")
        except RuntimeError as exc:
            add("checkpoints", False, str(exc))
    else:
        add("checkpoints", False, "not checked because native ComfyUI is offline", severity="warning")

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
        "endpoint": endpoint,
        "mcp_http": f"http://{mcp_host}:{mcp_port}/mcp",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO Claude/ChatGPT agent integration doctor")
    parser.add_argument("--repair", action="store_true", help="Start a discovered native ComfyUI when offline")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--mcp-host", default=DEFAULT_MCP_HOST)
    parser.add_argument("--mcp-port", type=int, default=DEFAULT_MCP_PORT)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.mcp_port <= 65535:
        parser.error("--mcp-port must be between 1 and 65535")
    payload = run(args.repair, args.endpoint.rstrip("/"), args.mcp_host, args.mcp_port, not args.skip_tests)
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
