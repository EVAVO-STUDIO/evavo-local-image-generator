"""Validated entrypoint for the EVAVO MCP v2 server.

Supported Claude/ChatGPT/local launches enter here so owner-granted filesystem
and local-backend authority is checked before the long-lived MCP server starts.
The underlying ``mcp_server`` module remains importable for unit/integration
testing and tool implementation, but production profiles should launch this
module.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .mcp_policy import validate_environment


def validate_startup_policy() -> dict[str, Any]:
    result = validate_environment()
    if not result.get("ok"):
        errors = result.get("errors") if isinstance(result.get("errors"), list) else []
        detail = "; ".join(str(item) for item in errors) or "unknown MCP production policy error"
        raise RuntimeError(f"MCP_POLICY_INVALID:{detail}")
    return result


def apply_validated_policy(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize validated authority into this process before importing MCP."""
    policy = result.get("policy")
    if not isinstance(policy, dict):
        raise RuntimeError("MCP_POLICY_INVALID:validated policy payload is missing")

    required = {
        "comfyui_endpoint": policy.get("comfyui_endpoint"),
        "default_output_root": policy.get("default_output_root"),
        "task_history_file": policy.get("task_history_file"),
    }
    missing = [name for name, value in required.items() if not isinstance(value, str) or not value]
    if missing:
        raise RuntimeError(f"MCP_POLICY_INVALID:validated policy is missing {', '.join(missing)}")

    os.environ["COMFYUI_ENDPOINT"] = str(required["comfyui_endpoint"])
    os.environ.pop("EVAVO_COMFYUI_ENDPOINT", None)
    os.environ["EVAVO_GENERATION_OUTPUT_DIR"] = str(required["default_output_root"])
    os.environ["EVAVO_TASK_HISTORY"] = str(required["task_history_file"])

    additional = policy.get("additional_output_roots")
    roots = [str(item) for item in additional] if isinstance(additional, list) else []
    if roots:
        os.environ["EVAVO_MCP_OUTPUT_ROOTS"] = os.pathsep.join(roots)
    else:
        os.environ.pop("EVAVO_MCP_OUTPUT_ROOTS", None)

    owner_workflow = policy.get("owner_workflow")
    if isinstance(owner_workflow, str) and owner_workflow:
        os.environ["EVAVO_COMFYUI_WORKFLOW"] = owner_workflow
    else:
        os.environ.pop("EVAVO_COMFYUI_WORKFLOW", None)

    if bool(policy.get("tool_workflow_paths_allowed")):
        workflow_root = policy.get("tool_workflow_root")
        if not isinstance(workflow_root, str) or not workflow_root:
            raise RuntimeError("MCP_POLICY_INVALID:tool workflow authority lacks a validated root")
        os.environ["EVAVO_MCP_ALLOW_WORKFLOW_PATHS"] = "1"
        os.environ["EVAVO_MCP_WORKFLOW_ROOT"] = workflow_root
    else:
        os.environ.pop("EVAVO_MCP_ALLOW_WORKFLOW_PATHS", None)
        os.environ.pop("EVAVO_MCP_WORKFLOW_ROOT", None)

    return policy


def main() -> None:
    try:
        result = validate_startup_policy()
        apply_validated_policy(result)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(78) from exc

    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    for warning in warnings:
        print(f"MCP_POLICY_WARNING:{warning}", file=sys.stderr)

    # Import only after validation + normalization so invalid or ambiguous local
    # authority cannot partially initialize the MCP server/tool implementation.
    from .mcp_server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
