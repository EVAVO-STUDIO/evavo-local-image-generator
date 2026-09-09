"""Safe per-prompt cancellation for native ComfyUI."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict

from .backends import ComfyUIBackend
from .comfyui_status import prompt_status


def _post_legacy_queue_delete(backend: ComfyUIBackend, prompt_id: str) -> None:
    """Use legacy pending-queue deletion without requiring a JSON response body."""
    with backend._open(
        "/queue",
        method="POST",
        payload={"delete": [prompt_id]},
        timeout=15.0,
    ) as response:
        response.read()


def cancel_prompt(backend: ComfyUIBackend, prompt_id: str) -> Dict[str, Any]:
    """Request cancellation of exactly one ComfyUI prompt.

    Modern ComfyUI's idempotent jobs cancel endpoint is preferred. On older
    servers EVAVO may delete a prompt only when status reconciliation first
    proves that exact prompt is pending. Running legacy jobs are deliberately
    not interrupted through broad ``/interrupt`` because that endpoint can
    affect work beyond the requested task on older deployments.
    """
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError("prompt_id must be a non-empty string")
    prompt_id = prompt_id.strip()

    before = prompt_status(backend, prompt_id)
    before_status = str(before.get("status") or "unknown")
    if before_status in {"completed", "failed", "cancelled"}:
        return {
            "ok": True,
            "task_id": prompt_id,
            "status": before_status,
            "cancelled": before_status == "cancelled",
            "cancel_requested": False,
            "method": "terminal_noop",
            "previous_status": before_status,
            "state": before,
        }
    if before_status == "unknown":
        return {
            "ok": True,
            "task_id": prompt_id,
            "status": "unknown",
            "cancelled": False,
            "cancel_requested": False,
            "method": "unknown_noop",
            "previous_status": "unknown",
            "state": before,
        }

    encoded = urllib.parse.quote(prompt_id, safe="")
    try:
        response = backend._request(
            f"/api/jobs/{encoded}/cancel",
            method="POST",
            payload={},
            timeout=15.0,
        )
    except RuntimeError as exc:
        if not str(exc).startswith("COMFYUI_HTTP_ERROR:404:"):
            raise
        if before_status == "queued":
            _post_legacy_queue_delete(backend, prompt_id)
            return {
                "ok": True,
                "task_id": prompt_id,
                "status": "cancelled",
                "cancelled": True,
                "cancel_requested": True,
                "method": "legacy_pending_queue_delete",
                "previous_status": before_status,
                "state": before,
            }
        return {
            "ok": False,
            "task_id": prompt_id,
            "status": before_status,
            "cancelled": False,
            "cancel_requested": False,
            "method": "legacy_running_unsupported",
            "previous_status": before_status,
            "error_code": "COMFYUI_TARGETED_CANCEL_UNSUPPORTED",
            "message": (
                "This ComfyUI version does not expose per-job cancellation. "
                "EVAVO will not use broad /interrupt for a running job; upgrade ComfyUI to cancel it safely."
            ),
            "state": before,
        }

    dispatched = response.get("cancelled") is True
    if not dispatched:
        after = prompt_status(backend, prompt_id)
        return {
            "ok": True,
            "task_id": prompt_id,
            "status": str(after.get("status") or before_status),
            "cancelled": str(after.get("status")) == "cancelled",
            "cancel_requested": False,
            "method": "jobs_cancel_noop",
            "previous_status": before_status,
            "state": after,
        }

    # Pending cancellation is a dequeue and can be treated as final immediately.
    if before_status == "queued":
        return {
            "ok": True,
            "task_id": prompt_id,
            "status": "cancelled",
            "cancelled": True,
            "cancel_requested": True,
            "method": "jobs_cancel",
            "previous_status": before_status,
            "state": before,
        }

    # Running cancellation is dispatched atomically by modern ComfyUI but may
    # take effect only at a node/step boundary. Re-read status without claiming
    # terminal cancellation until ComfyUI reports it.
    after = prompt_status(backend, prompt_id)
    after_status = str(after.get("status") or "running")
    final_cancelled = after_status == "cancelled"
    return {
        "ok": True,
        "task_id": prompt_id,
        "status": "cancelled" if final_cancelled else "cancel_requested",
        "backend_status": after_status,
        "cancelled": final_cancelled,
        "cancel_requested": True,
        "method": "jobs_cancel",
        "previous_status": before_status,
        "state": after,
    }
