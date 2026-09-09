"""Validated entrypoint for the EVAVO MCP v2 server.

Supported Claude/ChatGPT/local launches enter here so owner-granted filesystem
authority is checked before the long-lived MCP server starts. The underlying
``mcp_server`` module remains importable for unit/integration testing and tool
implementation, but production profiles should launch this module.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .mcp_policy import validate_environment


def validate_startup_policy() -> dict[str, Any]:
    result = validate_environment()
    if not result.get("ok"):
        errors = result.get("errors") if isinstance(result.get("errors"), list) else []
        detail = "; ".join(str(item) for item in errors) or "unknown MCP filesystem policy error"
        raise RuntimeError(f"MCP_POLICY_INVALID:{detail}")
    return result


def main() -> None:
    try:
        policy = validate_startup_policy()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(78) from exc

    warnings = policy.get("warnings") if isinstance(policy.get("warnings"), list) else []
    for warning in warnings:
        print(f"MCP_POLICY_WARNING:{warning}", file=sys.stderr)

    # Import only after policy validation so an invalid local authority contract
    # cannot start a partially initialized MCP server.
    from .mcp_server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
