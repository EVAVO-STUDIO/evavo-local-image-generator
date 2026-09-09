"""Agent-safe orchestration for ComfyUI dependency repair.

The actual package synchronization remains in the repository's bounded
``repair-comfyui-dependencies.py`` command. This module turns that command into
an agent/library primitive without giving MCP callers arbitrary package, Python,
or filesystem authority.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, Optional

from .comfyui_runtime import (
    LAST_FAILURE_FILE,
    STATE_DIR,
    classify_startup_output,
    load_last_failure,
)

ROOT = Path(__file__).resolve().parents[1]
REPAIR_SCRIPT = ROOT / "repair-comfyui-dependencies.py"
DIAGNOSTIC_OUTPUT_FILE = STATE_DIR / "comfy-startup-output.txt"
DEFAULT_CORE_MODULE = "comfy_aimdo"
_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MAX_DIAGNOSTIC_BYTES = 256 * 1024


def _validated_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be a number") from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
        raise ValueError("timeout_seconds must be finite, greater than 0 and at most 3600")
    return timeout


def _missing_module_from_failure(failure: Dict[str, Any]) -> Optional[str]:
    if failure.get("category") != "missing_dependency":
        return None
    modules = failure.get("missing_modules")
    if not isinstance(modules, list):
        return None
    for raw in modules:
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate and _MODULE_PATTERN.fullmatch(candidate):
                return candidate
    return None


def _regular_file_mtime(path: Path) -> int:
    try:
        if path.is_symlink() or not path.is_file():
            return -1
        return int(path.stat().st_mtime_ns)
    except OSError:
        return -1


def _diagnostic_log_evidence(path: Optional[Path] = None) -> Dict[str, Any]:
    """Classify the latest bounded diagnostic log without trusting arbitrary paths."""
    target = path or DIAGNOSTIC_OUTPUT_FILE
    try:
        if target.is_symlink() or not target.is_file():
            return {}
        size = target.stat().st_size
        with target.open("rb") as handle:
            if size > _MAX_DIAGNOSTIC_BYTES:
                handle.seek(max(0, size - _MAX_DIAGNOSTIC_BYTES))
            text = handle.read(_MAX_DIAGNOSTIC_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return {}
    if not text.strip():
        return {}
    result = classify_startup_output(
        text,
        returncode=None,
        health_ready=False,
        timed_out=False,
        port_was_open=False,
    )
    result["evidence_source"] = "bounded_diagnostic_log"
    result["evidence_path"] = str(target)
    return result


def _latest_repair_evidence() -> Dict[str, Any]:
    """Choose the newest EVAVO-owned structured/log startup evidence.

    ``diagnose_backend`` returns evidence directly to its caller and writes the
    bounded diagnostic log. ``ensure_backend`` persists the structured last
    failure document. Repair must accept either path while refusing stale data
    when a newer diagnostic exists.
    """
    persisted = load_last_failure()
    persisted = dict(persisted) if isinstance(persisted, dict) else {}
    if persisted:
        persisted.setdefault("evidence_source", "persisted_startup_failure")
        persisted.setdefault("evidence_path", str(LAST_FAILURE_FILE))

    diagnostic = _diagnostic_log_evidence()
    persisted_mtime = _regular_file_mtime(LAST_FAILURE_FILE)
    diagnostic_mtime = _regular_file_mtime(DIAGNOSTIC_OUTPUT_FILE)

    if diagnostic and diagnostic_mtime >= 0 and diagnostic_mtime > persisted_mtime:
        return diagnostic
    if persisted:
        return persisted
    return diagnostic


def build_repair_command(
    *,
    module: str,
    timeout_seconds: float,
    force_sync: bool = False,
    verify_only: bool = False,
) -> list[str]:
    """Build the bounded repair command without invoking a shell."""
    if not _MODULE_PATTERN.fullmatch(module):
        raise ValueError(f"invalid Python module name: {module!r}")
    timeout = _validated_timeout(timeout_seconds)
    command = [
        sys.executable,
        str(REPAIR_SCRIPT),
        "--module",
        module,
        "--timeout",
        f"{timeout:g}",
    ]
    if force_sync:
        command.append("--force-sync")
    if verify_only:
        command.append("--verify-only")
    return command


def _parse_json_stdout(stdout: str) -> Optional[Dict[str, Any]]:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def repair_backend_dependencies(
    *,
    timeout_seconds: float = 900.0,
    force_sync: bool = False,
    verify_only: bool = False,
) -> Dict[str, Any]:
    """Repair the discovered native ComfyUI from its own requirements file.

    Normal mutation is admitted only when the newest EVAVO-owned startup
    evidence is a core ``missing_dependency`` failure. Custom-node dependency
    failures are deliberately not repaired through core ComfyUI requirements.
    ``force_sync`` is an explicit operator/agent override that still uses only
    the checkout's own requirements and selected ComfyUI interpreter.
    """
    timeout = _validated_timeout(timeout_seconds)
    failure = _latest_repair_evidence()
    category = str(failure.get("category") or "none")
    missing_modules = failure.get("missing_modules") if isinstance(failure.get("missing_modules"), list) else []
    evidence_source = str(failure.get("evidence_source") or "none")
    evidence_path = failure.get("evidence_path")

    if category == "custom_node_dependency" and not force_sync:
        return {
            "ok": False,
            "status": "custom_node_repair_required",
            "error_code": "CUSTOM_NODE_DEPENDENCY",
            "message": "The startup failure belongs to a custom node. Core ComfyUI requirements were not modified.",
            "source_failure_category": category,
            "missing_modules": missing_modules,
            "evidence_source": evidence_source,
            "evidence_path": evidence_path,
            "repair_performed": False,
        }

    module = _missing_module_from_failure(failure)
    if module is None:
        if force_sync or verify_only:
            module = DEFAULT_CORE_MODULE
        else:
            return {
                "ok": False,
                "status": "no_repair_evidence",
                "error_code": "NO_REPAIR_EVIDENCE",
                "message": "Run diagnose_backend first. Dependency mutation is admitted only for current structured/bounded missing_dependency evidence.",
                "source_failure_category": category,
                "missing_modules": missing_modules,
                "evidence_source": evidence_source,
                "evidence_path": evidence_path,
                "repair_performed": False,
            }

    if not REPAIR_SCRIPT.is_file():
        return {
            "ok": False,
            "status": "repair_script_missing",
            "error_code": "REPAIR_SCRIPT_MISSING",
            "message": f"Dependency repair command is missing: {REPAIR_SCRIPT}",
            "source_failure_category": category,
            "missing_modules": missing_modules,
            "evidence_source": evidence_source,
            "evidence_path": evidence_path,
            "repair_performed": False,
        }

    command = build_repair_command(
        module=module,
        timeout_seconds=timeout,
        force_sync=force_sync,
        verify_only=verify_only,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 30.0,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "repair_timeout",
            "error_code": "REPAIR_TIMEOUT",
            "message": "Dependency repair exceeded its bounded execution deadline.",
            "source_failure_category": category,
            "missing_modules": missing_modules,
            "evidence_source": evidence_source,
            "evidence_path": evidence_path,
            "target_module": module,
            "repair_performed": False,
            "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
            "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {
            "ok": False,
            "status": "repair_launch_failed",
            "error_code": "REPAIR_LAUNCH_FAILED",
            "message": f"{type(exc).__name__}: {exc}",
            "source_failure_category": category,
            "missing_modules": missing_modules,
            "evidence_source": evidence_source,
            "evidence_path": evidence_path,
            "target_module": module,
            "repair_performed": False,
        }

    payload = _parse_json_stdout(completed.stdout)
    if payload is None:
        return {
            "ok": False,
            "status": "repair_invalid_receipt",
            "error_code": "REPAIR_INVALID_RECEIPT",
            "message": "Dependency repair did not return its required JSON receipt.",
            "source_failure_category": category,
            "missing_modules": missing_modules,
            "evidence_source": evidence_source,
            "evidence_path": evidence_path,
            "target_module": module,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "repair_performed": False,
        }

    result = dict(payload)
    result["source_failure_category"] = category
    result["source_missing_modules"] = missing_modules
    result["evidence_source"] = evidence_source
    result["evidence_path"] = evidence_path
    result["target_module"] = module
    result["returncode"] = completed.returncode
    result["agent_safe"] = True
    result["used_checkout_requirements"] = True
    result["used_shell"] = False
    if completed.returncode != 0:
        result["ok"] = False
    return result


__all__ = ["build_repair_command", "repair_backend_dependencies"]
