#!/usr/bin/env python3
"""Cross-platform structural and test verifier for EVAVO local image generation.

This verifier is intentionally read-only. It checks the critical repository
contract, compiles Python sources in memory, optionally asks PowerShell to parse
the canonical Windows scripts, and can run every root ``test-*.py`` suite.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent

CRITICAL_FILES: Sequence[str] = (
    "evavo.py",
    "verify-evavo.py",
    "evavo_operations.py",
    "evavo-wrapper.py",
    "generate-batch.py",
    "monitor-evavo.py",
    "task-tracker.py",
    "mock-comfyui-server.py",
    "provision-comfyui.py",
    "agent-doctor.py",
    "test-operations.py",
    "test-provisioning.py",
    "test-backend-automation.py",
    "test-batch-workflow-preflight.py",
    "test-agent-integration.py",
    "test-agent-doctor-workflows.py",
    "test-chatgpt-tunnel.py",
    "UPDATE-AND-VERIFY-EVAVO.ps1",
    "INSTALL-CLAUDE-MCP.ps1",
    "START-AGENT-MCP.ps1",
    "INSTALL-AGENT-MCP-AUTOSTART.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "START-CHATGPT-MCP-TUNNEL.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "CHATGPT-TUNNEL-DOCTOR.ps1",
    "README.md",
    "AGENT-INTEGRATION.md",
    "CHATGPT-TUNNEL.md",
    "QUICK-REFERENCE.md",
    "evavo_local_image_generator/backends/comfyui_backend.py",
    "evavo_local_image_generator/comfyui_runtime.py",
    "evavo_local_image_generator/mcp_server.py",
)

POWERSHELL_SCRIPTS: Sequence[str] = (
    "UPDATE-AND-VERIFY-EVAVO.ps1",
    "INSTALL-CLAUDE-MCP.ps1",
    "START-AGENT-MCP.ps1",
    "INSTALL-AGENT-MCP-AUTOSTART.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "START-CHATGPT-MCP-TUNNEL.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "CHATGPT-TUNNEL-DOCTOR.ps1",
)


def _result(name: str, ok: bool, detail: str, *, severity: str = "error", skipped: bool = False) -> Dict[str, Any]:
    return {"name": name, "ok": ok, "severity": severity, "skipped": skipped, "detail": detail}


def discover_tests() -> List[str]:
    """Discover every root integration/safety suite by repository naming contract."""
    return sorted(path.name for path in ROOT.glob("test-*.py") if path.is_file())


def _critical_python_files() -> List[Path]:
    paths = [ROOT / name for name in CRITICAL_FILES if name.endswith(".py")]
    package = ROOT / "evavo_local_image_generator"
    if package.is_dir():
        paths.extend(path for path in package.rglob("*.py") if "__pycache__" not in path.parts)
    unique: List[Path] = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return sorted(unique)


def verify_files() -> Dict[str, Any]:
    missing = [name for name in CRITICAL_FILES if not (ROOT / name).is_file()]
    return _result("critical_files", not missing, "all present" if not missing else "missing: " + ", ".join(missing))


def verify_python_compile() -> Dict[str, Any]:
    """Parse/compile Python sources in memory without creating __pycache__."""
    failures: List[str] = []
    checked = 0
    for path in _critical_python_files():
        if not path.is_file():
            continue
        checked += 1
        try:
            with tokenize.open(path) as handle:
                source = handle.read()
            compile(source, str(path), "exec", dont_inherit=True)
        except (OSError, SyntaxError, UnicodeError, tokenize.TokenError) as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    detail = f"compiled {checked} Python files in memory"
    if failures:
        detail += "; failures: " + " | ".join(failures[:20])
    return _result("python_compile", not failures, detail)


def _powershell_executable() -> str | None:
    candidates = ("pwsh.exe", "powershell.exe", "pwsh", "powershell") if os.name == "nt" else ("pwsh", "powershell")
    return next((path for name in candidates if (path := shutil.which(name))), None)


def verify_powershell_syntax(require: bool) -> Dict[str, Any]:
    executable = _powershell_executable()
    if not executable:
        severity = "error" if require else "warning"
        return _result(
            "powershell_syntax",
            not require,
            "PowerShell not available in this environment; the canonical Windows updater requires this check before configuration writes",
            severity=severity,
            skipped=not require,
        )

    failures: List[str] = []
    checked = 0
    for name in POWERSHELL_SCRIPTS:
        path = (ROOT / name).resolve()
        if not path.is_file():
            failures.append(f"{name}: missing")
            continue
        checked += 1
        escaped = str(path).replace("'", "''")
        script = (
            "$tokens=$null; $errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors -and $errors.Count -gt 0) { "
            "$errors | ForEach-Object { Write-Error (('{0}:{1} {2}' -f $_.Extent.StartLineNumber,$_.Extent.StartColumnNumber,$_.Message)) }; exit 2 }; exit 0"
        )
        try:
            completed = subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", script],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}: {exc}")
            continue
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().replace("\n", " | ")
            failures.append(f"{name}: {detail[-1200:] or f'exit {completed.returncode}'}")

    detail = f"parsed {checked} PowerShell scripts with {executable}"
    if failures:
        detail += "; failures: " + " | ".join(failures[:20])
    return _result("powershell_syntax", not failures, detail)


def run_tests(tests: Iterable[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for name in tests:
        path = ROOT / name
        if not path.is_file():
            results.append(_result(f"test:{name}", False, "missing"))
            continue
        try:
            completed = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            results.append(_result(f"test:{name}", False, "timed out after 900 seconds"))
            continue
        except OSError as exc:
            results.append(_result(f"test:{name}", False, str(exc)))
            continue
        output = (completed.stdout + "\n" + completed.stderr).strip()
        tail = output[-2400:] if output else "no output"
        results.append(_result(f"test:{name}", completed.returncode == 0, f"exit={completed.returncode}; {tail}"))
    return results


def verify(*, full: bool, require_powershell: bool) -> Dict[str, Any]:
    tests = discover_tests()
    checks = [verify_files(), verify_python_compile(), verify_powershell_syntax(require_powershell)]
    if full:
        checks.append(
            _result(
                "test_inventory",
                bool(tests),
                f"discovered {len(tests)} root suites: {', '.join(tests)}" if tests else "no root test-*.py suites found",
            )
        )
        checks.extend(run_tests(tests))
    hard_failures = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["ok"] and item["severity"] == "warning"]
    return {
        "ok": not hard_failures,
        "status": "verified" if not hard_failures and not warnings else ("verified_with_warnings" if not hard_failures else "failed"),
        "root": str(ROOT),
        "python": sys.executable,
        "full": full,
        "discovered_tests": tests,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify EVAVO repository/runtime contracts without mutating workstation configuration")
    parser.add_argument("--full", action="store_true", help="Run every discovered root test-*.py suite after structural checks")
    parser.add_argument("--require-powershell", action="store_true", help="Fail when PowerShell is unavailable instead of reporting a skipped warning")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    payload = verify(full=args.full, require_powershell=args.require_powershell)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("EVAVO repository verifier")
        print("=" * 88)
        for check in payload["checks"]:
            if check.get("skipped"):
                marker = "SKIP"
            elif check["ok"]:
                marker = "OK"
            elif check["severity"] == "warning":
                marker = "WARN"
            else:
                marker = "FAIL"
            print(f"[{marker:<4}] {check['name']:<34} {check['detail']}")
        print("=" * 88)
        print(payload["status"])
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
