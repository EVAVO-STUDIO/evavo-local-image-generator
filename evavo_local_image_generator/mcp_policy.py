"""Read-only validation for EVAVO MCP authority configuration.

This module intentionally performs no repair and creates no directories. It is
safe for the repository verifier, installers and agent diagnostics to call
before they persist or launch MCP configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUE_VALUES = {"1", "true", "yes", "on"}
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_COMFYUI_ENDPOINT = "http://127.0.0.1:8188"


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def _lexical_absolute(value: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _existing_directory(value: str | Path, *, label: str, writable: bool = False) -> Path:
    lexical = _lexical_absolute(value)
    if lexical.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} does not exist: {lexical}") from exc
    if not _same_path(lexical, resolved):
        raise ValueError(f"{label} traverses a symlink or redirected parent path")
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    if writable and not os.access(resolved, os.W_OK):
        raise ValueError(f"{label} is not writable: {resolved}")
    return resolved


def _existing_file(value: str | Path, *, label: str) -> Path:
    lexical = _lexical_absolute(value)
    if lexical.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} does not exist: {lexical}") from exc
    if not _same_path(lexical, resolved):
        raise ValueError(f"{label} traverses a symlink or redirected parent path")
    if not resolved.is_file():
        raise ValueError(f"{label} must be an existing ordinary file")
    return resolved


def _split_roots(raw: str) -> list[str]:
    """Split owner root lists without breaking Windows drive-letter paths.

    Windows uses semicolons for multiple roots. POSIX commonly uses ``:``. A
    copied single Windows path such as ``D:\\Renders`` must remain one value
    even when this validator is executed on a POSIX test/automation host.
    """
    text = raw.strip()
    if not text:
        return []
    if ";" in text:
        return [item.strip() for item in text.split(";") if item.strip()]
    if os.pathsep == ":" and _WINDOWS_DRIVE_PATH.match(text):
        return [text]
    return [item.strip() for item in text.split(os.pathsep) if item.strip()]


def _creatable_output_root(value: str | Path, *, label: str) -> Path:
    """Validate a default output root without creating it.

    The default EVAVO output directory may legitimately not exist yet. In that
    case validate the nearest existing ancestor and require it to be writable.
    Explicit *additional* MCP roots must already exist and be writable.
    """
    lexical = _lexical_absolute(value)
    if lexical.exists() or lexical.is_symlink():
        return _existing_directory(lexical, label=label, writable=True)

    ancestor = lexical.parent
    while ancestor != ancestor.parent and not ancestor.exists() and not ancestor.is_symlink():
        ancestor = ancestor.parent
    if ancestor.is_symlink():
        raise ValueError(f"{label} parent path must not traverse a symlink: {ancestor}")
    try:
        resolved_ancestor = ancestor.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} has no usable existing parent: {lexical}") from exc
    if not _same_path(ancestor, resolved_ancestor):
        raise ValueError(f"{label} parent path traverses a symlink or redirected path")
    if not resolved_ancestor.is_dir():
        raise ValueError(f"{label} parent must be a directory: {resolved_ancestor}")
    if not os.access(resolved_ancestor, os.W_OK):
        raise ValueError(f"{label} parent is not writable: {resolved_ancestor}")
    return lexical


def _validated_comfyui_endpoint() -> tuple[str, list[str]]:
    """Return the canonical local ComfyUI endpoint allowed for production MCP.

    Production Claude/ChatGPT MCP is a local image-generation service. Prompt
    traffic must not silently leave the workstation because an inherited env var
    points at a remote host. Library/testing code may instantiate backends
    directly when a different network contract is intentionally required.
    """
    warnings: list[str] = []
    canonical = os.getenv("COMFYUI_ENDPOINT", "").strip()
    legacy = os.getenv("EVAVO_COMFYUI_ENDPOINT", "").strip()
    raw = canonical or legacy or DEFAULT_COMFYUI_ENDPOINT
    if canonical and legacy and canonical.rstrip("/") != legacy.rstrip("/"):
        warnings.append("EVAVO_COMFYUI_ENDPOINT differs from canonical COMFYUI_ENDPOINT and is ignored")
    elif not canonical and legacy:
        warnings.append("legacy EVAVO_COMFYUI_ENDPOINT is accepted as migration input; persist COMFYUI_ENDPOINT instead")

    try:
        parsed = urllib.parse.urlparse(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"COMFYUI_ENDPOINT is invalid: {raw}") from exc

    if parsed.scheme != "http":
        raise ValueError("COMFYUI_ENDPOINT must use http for the local native ComfyUI service")
    if parsed.username or parsed.password:
        raise ValueError("COMFYUI_ENDPOINT must not contain credentials")
    if not parsed.hostname or parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        raise ValueError("COMFYUI_ENDPOINT must target loopback (127.0.0.1, localhost, or ::1) for production MCP")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("COMFYUI_ENDPOINT must contain only scheme, loopback host and optional port")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("COMFYUI_ENDPOINT port must be between 1 and 65535")

    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if host == "::1" else host
    rendered_port = f":{port}" if port is not None else ""
    return f"http://{rendered_host}{rendered_port}", warnings


def validate_environment() -> dict[str, Any]:
    """Validate explicitly configured production MCP authority, read-only."""
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    try:
        comfyui_endpoint, endpoint_warnings = _validated_comfyui_endpoint()
        details["comfyui_endpoint"] = comfyui_endpoint
        warnings.extend(endpoint_warnings)
    except ValueError as exc:
        errors.append(str(exc))
        details["comfyui_endpoint"] = None

    default_output_raw = os.getenv("EVAVO_GENERATION_OUTPUT_DIR", "").strip()
    default_output = default_output_raw or str(REPO_ROOT / ".evavo" / "outputs")
    try:
        validated_default = _creatable_output_root(default_output, label="EVAVO_GENERATION_OUTPUT_DIR")
        details["default_output_root"] = str(validated_default)
    except ValueError as exc:
        errors.append(str(exc))

    additional_raw = os.getenv("EVAVO_MCP_OUTPUT_ROOTS", "").strip()
    additional: list[str] = []
    for index, raw in enumerate(_split_roots(additional_raw)):
        try:
            root = _existing_directory(raw, label=f"EVAVO_MCP_OUTPUT_ROOTS[{index}]", writable=True)
            additional.append(str(root))
        except ValueError as exc:
            errors.append(str(exc))
    details["additional_output_roots"] = additional

    owner_workflow_raw = os.getenv("EVAVO_COMFYUI_WORKFLOW", "").strip()
    if owner_workflow_raw:
        try:
            details["owner_workflow"] = str(
                _existing_file(owner_workflow_raw, label="EVAVO_COMFYUI_WORKFLOW")
            )
        except ValueError as exc:
            errors.append(str(exc))
    else:
        details["owner_workflow"] = None

    tool_workflows_allowed = _truthy("EVAVO_MCP_ALLOW_WORKFLOW_PATHS")
    details["tool_workflow_paths_allowed"] = tool_workflows_allowed
    workflow_root_raw = os.getenv("EVAVO_MCP_WORKFLOW_ROOT", "").strip()
    if tool_workflows_allowed:
        if not workflow_root_raw:
            errors.append(
                "EVAVO_MCP_WORKFLOW_ROOT is required when EVAVO_MCP_ALLOW_WORKFLOW_PATHS is enabled"
            )
            details["tool_workflow_root"] = None
        else:
            try:
                details["tool_workflow_root"] = str(
                    _existing_directory(workflow_root_raw, label="EVAVO_MCP_WORKFLOW_ROOT")
                )
            except ValueError as exc:
                errors.append(str(exc))
                details["tool_workflow_root"] = None
    else:
        details["tool_workflow_root"] = None
        if workflow_root_raw:
            warnings.append(
                "EVAVO_MCP_WORKFLOW_ROOT is configured but tool workflow paths are disabled; the root grants no tool authority"
            )

    return {
        "ok": not errors,
        "status": "ready" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "policy": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate EVAVO MCP production authority without mutating the workstation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate_environment()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("EVAVO MCP production policy:", result["status"])
        for error in result["errors"]:
            print("ERROR:", error)
        for warning in result["warnings"]:
            print("WARNING:", warning)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
