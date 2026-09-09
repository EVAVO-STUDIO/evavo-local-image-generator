#!/usr/bin/env python3
"""Authoritative read-only verifier for EVAVO local image generation.

The verifier checks critical repository contracts, compiles Python sources in
memory, parses supported PowerShell scripts when available, validates retained
compatibility entry points, and runs every modern test suite across the root,
``tests/`` and package test surfaces.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

ROOT = Path(__file__).resolve().parent
DEFAULT_TEST_TIMEOUT_SECONDS = 300.0
MIN_TEST_TIMEOUT_SECONDS = 10.0
MAX_TEST_TIMEOUT_SECONDS = 1800.0

CRITICAL_FILES: Sequence[str] = (
    ".mcp.json",
    ".evavo/capabilities.json",
    "EVAVO-CAPABILITIES.json",
    "evavo.py",
    "verify-evavo.py",
    "safe_main_git.py",
    "safe_git_main.py",
    "evavo_operations.py",
    "evavo-wrapper.py",
    "generate-batch.py",
    "monitor-evavo.py",
    "task-tracker.py",
    "mock-comfyui-server.py",
    "provision-comfyui.py",
    "agent-doctor.py",
    "legacy_image_cli.py",
    "claude_control.py",
    "EVAVO-GATEWAY.py",
    "EVAVO-SERVICE-MANAGER.py",
    "gateway-smoke-test.py",
    "evavo_local_image_generator/provider_runner.py",
    "evavo_local_image_generator/backends/comfyui_backend.py",
    "evavo_local_image_generator/comfyui_runtime.py",
    "evavo_local_image_generator/comfyui_status.py",
    "evavo_local_image_generator/comfyui_cancel.py",
    "evavo_local_image_generator/mcp_server.py",
    "UPDATE-AND-VERIFY-EVAVO.ps1",
    "INSTALL-CLAUDE-MCP.ps1",
    "START-AGENT-MCP.ps1",
    "STOP-AGENT-MCP.ps1",
    "INSTALL-AGENT-MCP-AUTOSTART.ps1",
    "SETUP-CHATGPT-EVAVO.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "START-CHATGPT-MCP-TUNNEL.ps1",
    "STOP-CHATGPT-MCP-TUNNEL.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "CHATGPT-TUNNEL-DOCTOR.ps1",
    "AGENT-STATUS.ps1",
    "START-GATEWAY.ps1",
    "SETUP-MCP-INTEGRATION.ps1",
    "VERIFY-INSTALLATION.ps1",
    "START-EVERYTHING.ps1",
    "MASTER-AUTOMATION-CONTROLLER.ps1",
    "RUN-FULL-GENERATION.ps1",
    "START-SERVICES.ps1",
    "COMMIT-UPGRADE.ps1",
    "COMMIT_AND_PUSH.ps1",
    "PUSH-UPGRADE-TO-MAIN.ps1",
    "COMPLETE_EVAVO_GIT_COMMIT.ps1",
    "create_github_repo.ps1",
    "AUTO-COMMIT-AND-PUSH.py",
    "DO-THIS-TO-COMMIT.txt",
    "START-EVAVO-SERVICES.bat",
    "START-ALL-SERVICES-AND-GENERATE.bat",
    "FULL-GENERATION-START.bat",
    "START-AUTONOMOUS.bat",
    "EVAVO-GENERATE-NOW.bat",
    "START-GENERATION.bat",
    "run_full_generation.sh",
    "README.md",
    "CLAUDE.md",
    "AGENT-INTEGRATION.md",
    "AGENT-RECOVERY.md",
    "AUTOMATION-GUIDE.md",
    "AUTONOMOUS-AUTOMATION.md",
    "AUTONOMOUS_SETUP.md",
    "DEPLOYMENT-CHECKLIST.md",
    "GATEWAY-INTEGRATION-GUIDE.md",
    "GATEWAY-AUX-PROVIDERS.md",
    "PROVIDER-INTEGRATION-GUIDE.md",
    "OPERATIONS-GUIDE.md",
    "CHATGPT-TUNNEL.md",
    "QUICK-REFERENCE.md",
    "PROJECT_SUMMARY.md",
)

POWERSHELL_SCRIPTS: Sequence[str] = (
    "UPDATE-AND-VERIFY-EVAVO.ps1",
    "INSTALL-CLAUDE-MCP.ps1",
    "START-AGENT-MCP.ps1",
    "STOP-AGENT-MCP.ps1",
    "INSTALL-AGENT-MCP-AUTOSTART.ps1",
    "SETUP-CHATGPT-EVAVO.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL.ps1",
    "SAVE-CHATGPT-TUNNEL-KEY.ps1",
    "START-CHATGPT-MCP-TUNNEL.ps1",
    "STOP-CHATGPT-MCP-TUNNEL.ps1",
    "INSTALL-CHATGPT-MCP-TUNNEL-AUTOSTART.ps1",
    "CHATGPT-TUNNEL-DOCTOR.ps1",
    "AGENT-STATUS.ps1",
    "START-GATEWAY.ps1",
    "SETUP-MCP-INTEGRATION.ps1",
    "VERIFY-INSTALLATION.ps1",
    "START-EVERYTHING.ps1",
    "MASTER-AUTOMATION-CONTROLLER.ps1",
    "RUN-FULL-GENERATION.ps1",
    "START-SERVICES.ps1",
    "COMMIT-UPGRADE.ps1",
    "COMMIT_AND_PUSH.ps1",
    "PUSH-UPGRADE-TO-MAIN.ps1",
    "COMPLETE_EVAVO_GIT_COMMIT.ps1",
    "create_github_repo.ps1",
)

LEGACY_DELEGATION_MARKERS: Mapping[str, Sequence[str]] = {
    "run_autonomous.py": ("legacy_image_cli",),
    "EXECUTE-GENERATION.py": ("legacy_image_cli",),
    "LAUNCH-GENERATION.py": ("legacy_image_cli",),
    "RUN-GENERATION.py": ("legacy_image_cli",),
    "RUN-FULL-GENERATION.py": ("legacy_image_cli",),
    "LINUX_GENERATION_RUNNER.py": ("legacy_image_cli",),
    "start_and_generate.py": ("legacy_image_cli",),
    "demo_autonomous.py": ("legacy_image_cli",),
    "EVAVO-AUTOMATION.py": ("evavo.py", "agent-doctor.py"),
    "setup-production.py": ("verify", "agent-doctor.py"),
    "create-complete-production.py": ("verify", "agent-doctor.py"),
    "COMPLETE-MULTIMODAL-TEST.py": ("not_implemented", "evavo.py"),
    "TEST-ALL-AI-SYSTEMS.py": ("evavo.py", "agent-doctor.py"),
    "SETUP-MCP-INTEGRATION.ps1": ("INSTALL-CLAUDE-MCP.ps1",),
    "VERIFY-INSTALLATION.ps1": ("verify-evavo.py",),
    "START-EVERYTHING.ps1": ("UPDATE-AND-VERIFY-EVAVO.ps1", "evavo.py"),
    "MASTER-AUTOMATION-CONTROLLER.ps1": ("UPDATE-AND-VERIFY-EVAVO.ps1", "evavo.py"),
    "RUN-FULL-GENERATION.ps1": ("legacy_image_cli.py",),
    "START-SERVICES.ps1": ("agent-doctor.py", "--provision"),
    "START-EVAVO-SERVICES.bat": ("agent-doctor.py", "--provision", "evavo.py"),
    "START-ALL-SERVICES-AND-GENERATE.bat": ("agent-doctor.py", "--provision", "evavo.py"),
    "FULL-GENERATION-START.bat": ("agent-doctor.py", "--provision", "evavo.py"),
    "START-AUTONOMOUS.bat": ("agent-doctor.py", "--provision"),
    "EVAVO-GENERATE-NOW.bat": ("legacy_image_cli.py",),
    "START-GENERATION.bat": ("legacy_image_cli.py",),
    "run_full_generation.sh": ("legacy_image_cli.py",),
    "START-GATEWAY.ps1": ("EVAVO-SERVICE-MANAGER.py",),
    "AUTO-COMMIT-AND-PUSH.py": ("safe_main_git",),
    "COMMIT-UPGRADE.ps1": ("safe_main_git.py",),
    "COMMIT_AND_PUSH.ps1": ("safe_main_git.py",),
    "PUSH-UPGRADE-TO-MAIN.ps1": ("safe_main_git.py",),
    "COMPLETE_EVAVO_GIT_COMMIT.ps1": ("safe_main_git.py",),
    "create_github_repo.ps1": ("remote get-url origin", "no repository creation"),
    "DO-THIS-TO-COMMIT.txt": ("safe_main_git.py", "git pull --ff-only origin main"),
}

RETIRED_ACTIVE_PATTERNS: Sequence[str] = (
    "taskkill /f /im python.exe",
    "taskkill /im python.exe",
    "cmd /k",
    "-noexit",
    "create_new_console",
    "subprocess.popen",
    "ollama serve",
    "kokoro-fastapi",
    "register-scheduledtask",
    "mock_video_data",
    "shutil.copytree",
    "remove-item \".git\\index.lock\"",
    "remove-item -path .\\.git",
    "git init --initial-branch=main",
    "git config user.name",
    "git config user.email",
    "tar -xzf evavo-upgrade-commit.tar.gz",
    "expand-archive -path evavo-upgrade-commit.tar.gz",
    "gh repo create",
    "git push --force",
    "git push -f",
)


def _result(name: str, ok: bool, detail: str, *, severity: str = "error", skipped: bool = False) -> Dict[str, Any]:
    return {"name": name, "ok": ok, "severity": severity, "skipped": skipped, "detail": detail}


def _test_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("test timeout must be a number") from exc
    if not math.isfinite(timeout) or timeout < MIN_TEST_TIMEOUT_SECONDS or timeout > MAX_TEST_TIMEOUT_SECONDS:
        raise ValueError(
            f"test timeout must be finite and between {MIN_TEST_TIMEOUT_SECONDS:g} and {MAX_TEST_TIMEOUT_SECONDS:g} seconds"
        )
    return timeout


def discover_tests() -> List[str]:
    """Discover every maintained Python test surface deterministically."""
    paths = [path for path in ROOT.glob("test-*.py") if path.is_file()]
    paths.extend(path for path in ROOT.glob("test_*.py") if path.is_file())
    repository_tests = ROOT / "tests"
    if repository_tests.is_dir():
        paths.extend(path for path in repository_tests.glob("test_*.py") if path.is_file())
        paths.extend(path for path in repository_tests.glob("test-*.py") if path.is_file())
    package_tests = ROOT / "evavo_local_image_generator" / "tests"
    if package_tests.is_dir():
        paths.extend(path for path in package_tests.glob("test_*.py") if path.is_file())
        paths.extend(path for path in package_tests.glob("test-*.py") if path.is_file())
    return sorted({path.relative_to(ROOT).as_posix() for path in paths})


def _critical_python_files() -> List[Path]:
    paths = [ROOT / name for name in CRITICAL_FILES if name.endswith(".py")]
    package = ROOT / "evavo_local_image_generator"
    if package.is_dir():
        paths.extend(path for path in package.rglob("*.py") if "__pycache__" not in path.parts)
    tests_dir = ROOT / "tests"
    if tests_dir.is_dir():
        paths.extend(path for path in tests_dir.rglob("*.py") if "__pycache__" not in path.parts)
    unique: List[Path] = []
    seen: set[str] = set()
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
        detail += "; failures: " + " | ".join(failures[:30])
    return _result("python_compile", not failures, detail)


def _active_lines(source: str) -> List[str]:
    active: List[str] = []
    for raw in source.splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if not stripped or stripped.startswith("#") or lower.startswith("rem ") or stripped.startswith("::"):
            continue
        active.append(lower)
    return active


def verify_legacy_entrypoints() -> Dict[str, Any]:
    failures: List[str] = []
    checked = 0
    for name, markers in LEGACY_DELEGATION_MARKERS.items():
        path = ROOT / name
        if not path.is_file():
            failures.append(f"{name}: missing")
            continue
        checked += 1
        try:
            source_raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            failures.append(f"{name}: {exc}")
            continue
        source_lower = source_raw.lower()
        for marker in markers:
            if marker.lower() not in source_lower:
                failures.append(f"{name}: missing canonical delegation marker {marker!r}")
        active = _active_lines(source_raw)
        for pattern in RETIRED_ACTIVE_PATTERNS:
            if any(pattern in line for line in active):
                failures.append(f"{name}: contains retired active behavior {pattern!r}")
    detail = f"checked {checked} supported compatibility entry points"
    if failures:
        detail += "; failures: " + " | ".join(failures[:40])
    return _result("legacy_entrypoint_safety", not failures, detail)


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
            "PowerShell not available; canonical Windows setup requires this parse gate before configuration writes",
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
        detail += "; failures: " + " | ".join(failures[:30])
    return _result("powershell_syntax", not failures, detail)


def run_tests(tests: Iterable[str], *, timeout_seconds: float) -> List[Dict[str, Any]]:
    timeout_seconds = _test_timeout(timeout_seconds)
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
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            results.append(_result(f"test:{name}", False, f"timed out after {timeout_seconds:g} seconds"))
            continue
        except OSError as exc:
            results.append(_result(f"test:{name}", False, str(exc)))
            continue
        output = (completed.stdout + "\n" + completed.stderr).strip()
        tail = output[-2400:] if output else "no output"
        results.append(_result(f"test:{name}", completed.returncode == 0, f"exit={completed.returncode}; {tail}"))
    return results


def verify(*, full: bool, require_powershell: bool, test_timeout: float = DEFAULT_TEST_TIMEOUT_SECONDS) -> Dict[str, Any]:
    timeout_seconds = _test_timeout(test_timeout)
    tests = discover_tests()
    checks = [verify_files(), verify_python_compile(), verify_legacy_entrypoints(), verify_powershell_syntax(require_powershell)]
    if full:
        checks.append(
            _result(
                "test_inventory",
                bool(tests),
                (
                    f"discovered {len(tests)} suites; timeout={timeout_seconds:g}s each: {', '.join(tests)}"
                    if tests
                    else "no modern test suites found"
                ),
            )
        )
        checks.extend(run_tests(tests, timeout_seconds=timeout_seconds))
    hard_failures = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["ok"] and item["severity"] == "warning"]
    return {
        "ok": not hard_failures,
        "status": "verified" if not hard_failures and not warnings else ("verified_with_warnings" if not hard_failures else "failed"),
        "root": str(ROOT),
        "python": sys.executable,
        "full": full,
        "test_timeout_seconds": timeout_seconds,
        "discovered_tests": tests,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify EVAVO repository/runtime contracts without mutating workstation configuration")
    parser.add_argument("--full", action="store_true", help="Run every discovered root/repository/package safety and integration suite")
    parser.add_argument("--require-powershell", action="store_true", help="Fail when PowerShell is unavailable instead of reporting a skipped warning")
    parser.add_argument(
        "--test-timeout",
        type=float,
        default=os.getenv("EVAVO_VERIFY_TEST_TIMEOUT", str(DEFAULT_TEST_TIMEOUT_SECONDS)),
        help=f"Per-suite timeout in seconds ({MIN_TEST_TIMEOUT_SECONDS:g}-{MAX_TEST_TIMEOUT_SECONDS:g}; default {DEFAULT_TEST_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    try:
        timeout_seconds = _test_timeout(args.test_timeout)
    except ValueError as exc:
        parser.error(str(exc))
    payload = verify(full=args.full, require_powershell=args.require_powershell, test_timeout=timeout_seconds)
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
