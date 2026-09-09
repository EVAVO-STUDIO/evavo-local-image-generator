"""Read-only validation for EVAVO MCP filesystem authority configuration.

This module intentionally performs no repair and creates no directories. It is
safe for the repository verifier, installers and agent diagnostics to call
before they persist or launch MCP configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUE_VALUES = {"1", "true", "yes", "on"}
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


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


def validate_environment() -> dict[str, Any]:
    """Validate explicitly configured MCP filesystem authority, read-only."""
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

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
    parser = argparse.ArgumentParser(description="Validate EVAVO MCP filesystem policy without mutating the workstation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate_environment()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("EVAVO MCP filesystem policy:", result["status"])
        for error in result["errors"]:
            print("ERROR:", error)
        for warning in result["warnings"]:
            print("WARNING:", warning)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
