#!/usr/bin/env python3
"""One-shot evidence-gated ComfyUI dependency recovery for setup automation.

This is deliberately not a generic pip/package installer. It delegates to the
same constrained repair bridge exposed to MCP:

- normal mutation requires current EVAVO-owned ``missing_dependency`` evidence;
- the exact diagnosed/discovered ComfyUI workdir + interpreter are selected;
- custom-node dependency failures do not mutate core ComfyUI requirements;
- forced synchronization is not used by this command;
- no arbitrary package/module/path/URL arguments are accepted.

The canonical Windows updater may run this once after strict agent-doctor fails,
then rerun agent-doctor to prove that the real generation contract recovered.
"""

from __future__ import annotations

import argparse
import json
import math

from evavo_local_image_generator.comfyui_repair import repair_backend_dependencies


def _timeout(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0 or parsed > 3600:
        raise ValueError("timeout must be finite, greater than zero and at most 3600 seconds")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-gated EVAVO ComfyUI dependency recovery")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        timeout = _timeout(args.timeout)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    result = repair_backend_dependencies(
        timeout_seconds=timeout,
        force_sync=False,
        verify_only=False,
    )
    payload = {
        "ok": bool(result.get("ok")),
        "status": result.get("status", "unknown"),
        "repair": result,
        "next_step": "rerun_strict_doctor" if result.get("ok") else "manual_or_category_specific_recovery_required",
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("EVAVO ComfyUI evidence-gated recovery")
        print("=" * 72)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
