"""Agent-safe orchestration for ComfyUI dependency repair.

The actual package synchronization remains in the repository's bounded
``repair-comfyui-dependencies.py`` command.  This module turns that command into
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
from typing import Any, Dict, Optional, Sequence

from .comfyui_runtime import load_last_failure

ROOT = Path(__file__).resolve().parents[1]
REPAIR_SCRIPT = ROOT / "repair-comfyui-dependencies.py"
DEFAULT_CORE_MODULE = "comfy_aimdo"
_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


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

    Normal mutation is admitted only when the last structured startup failure is
    a core ``missing_dependency`` failure.  Custom-node dependency failures are
    deliberately not repaired through core ComfyUI requirements.  ``force_sync``
    is an explicit operator/agent override that still uses only the checkout's
    own requirements and selected ComfyUI interpreter.
    """
    timeout = _validated_timeout(timeout_seconds)
    failure = load_last_failure()
    failure = failure if isinstance(failure, dict) else {}
    category = str(failure.get("category") or "none")
    missing_modules = failure.get("missing_modules") if isinstance(failure.get("missing_modules"), list) else []

    if category == "custom_node_dependency" and not force_sync:
        return {
            "ok": False,
            "status": "custom_node_repair_required",
            "error_code": "CUSTOM_NODE_DEPENDENCY",
            "message": "The startup failure belongs to a custom node. Core ComfyUI requirements were not modified.",
            "source_failure_category": category,
            "missing_modules": missing_modules,
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
                "message": "Run diagnose_backend first. Dependency mutation is admitted only for a structured missing_dependency failure.",
                "source_failure_category": category,
                "missing_modules": missing_modules,
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
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "repair_timeout",
            "error_code": "REPAIR_TIMEOUT",
            "message": "Dependency repair exceeded its bounded execution deadline.",
            "source_failure_category": category,
            "missing_modules": missing_modules,
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
            "target_module": module,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "repair_performed": False,
        }

    result = dict(payload)
    result["source_failure_category"] = category
    result["source_missing_modules"] = missing_modules
    result["target_module"] = module
    result["returncode"] = completed.returncode
    result["agent_safe"] = True
    result["used_checkout_requirements"] = True
    result["used_shell"] = False
    if completed.returncode != 0:
        result["ok"] = False
    return result


__all__ = ["build_repair_command", "repair_backend_dependencies"]
