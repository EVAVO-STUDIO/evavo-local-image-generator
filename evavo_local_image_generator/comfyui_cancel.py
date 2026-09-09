"""Safe per-prompt cancellation for native ComfyUI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from evavo_operations import ROOT as OPERATIONS_ROOT, TaskTracker, now_iso

from .backends import ComfyUIBackend
from .comfyui_status import prompt_status


def _task_history_path() -> Path:
    raw = os.getenv("EVAVO_TASK_HISTORY", "").strip()
    return Path(raw).expanduser().resolve() if raw else (OPERATIONS_ROOT / "task_history.json").resolve()


def _audit_cancellation(prompt_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist cancellation evidence only when this task already exists locally.

    The cancellation primitive must not create synthetic task records for prompts
    that were queued outside EVAVO. A non-terminal cancel request remains
    ``running`` in shared history while recording request metadata; only a
    backend-confirmed cancellation becomes terminal ``cancelled``.
    """
    if not result.get("cancel_requested"):
        return result

    history_path = _task_history_path()
    if not history_path.is_file():
        return result

    try:
        tracker = TaskTracker(history_path)
        existing = tracker.get_task(prompt_id)
        if existing is None:
            return result

        method = str(result.get("method") or "targeted_cancel")
        backend_status = str(result.get("backend_status") or result.get("previous_status") or "unknown")
        timestamp = now_iso()
        status = str(result.get("status") or "unknown")

        if status == "cancel_requested":
            tracker.update_task(
                prompt_id,
                "running",
                cancel_requested_at=timestamp,
                cancel_method=method,
                backend_status=backend_status,
            )
        elif status == "cancelled":
            fields: Dict[str, Any] = {
                "cancel_method": method,
                "backend_status": backend_status,
                "cancelled_at": timestamp,
            }
            if not existing.get("cancel_requested_at"):
                fields["cancel_requested_at"] = timestamp
            tracker.update_task(prompt_id, "cancelled", **fields)
    except Exception as exc:
        result = dict(result)
        result["audit_warning"] = str(exc)
    return result


def cancel_prompt(
    backend: ComfyUIBackend,
    prompt_id: str,
    *,
    audit_history: bool = True,
) -> Dict[str, Any]:
    """Request cancellation of exactly one ComfyUI prompt.

    Modern ComfyUI's idempotent jobs cancel endpoint is preferred. On older
    servers EVAVO may delete a prompt only when status reconciliation first
    proves that exact prompt is pending. Running legacy jobs are deliberately
    not interrupted through broad ``/interrupt`` because that endpoint can
    affect work beyond the requested task on older deployments.

    When ``audit_history`` is enabled (the production default), cancellation
    request/terminal evidence is added only to an already-existing EVAVO task
    record. Library/unit callers may disable that shared-history side effect.
    """
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError("prompt_id must be a non-empty string")
    prompt_id = prompt_id.strip()

    def finish(result: Dict[str, Any]) -> Dict[str, Any]:
        return _audit_cancellation(prompt_id, result) if audit_history else result

    before = prompt_status(backend, prompt_id)
    before_status = str(before.get("status") or "unknown")
    if before_status in {"completed", "failed", "cancelled"}:
        return finish({
            "ok": True,
            "task_id": prompt_id,
            "status": before_status,
            "cancelled": before_status == "cancelled",
            "cancel_requested": False,
            "method": "terminal_noop",
            "previous_status": before_status,
            "state": before,
        })
    if before_status == "unknown":
        return finish({
            "ok": True,
            "task_id": prompt_id,
            "status": "unknown",
            "cancelled": False,
            "cancel_requested": False,
            "method": "unknown_noop",
            "previous_status": "unknown",
            "state": before,
        })

    try:
        response = backend.cancel_job(prompt_id)
    except RuntimeError as exc:
        if not str(exc).startswith("COMFYUI_HTTP_ERROR:404:"):
            raise
        if before_status == "queued":
            backend.delete_pending(prompt_id)
            return finish({
                "ok": True,
                "task_id": prompt_id,
                "status": "cancelled",
                "cancelled": True,
                "cancel_requested": True,
                "method": "legacy_pending_queue_delete",
                "previous_status": before_status,
                "state": before,
            })
        return finish({
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
        })

    dispatched = response.get("cancelled") is True
    if not dispatched:
        after = prompt_status(backend, prompt_id)
        return finish({
            "ok": True,
            "task_id": prompt_id,
            "status": str(after.get("status") or before_status),
            "cancelled": str(after.get("status")) == "cancelled",
            "cancel_requested": False,
            "method": "jobs_cancel_noop",
            "previous_status": before_status,
            "state": after,
        })

    if before_status == "queued":
        return finish({
            "ok": True,
            "task_id": prompt_id,
            "status": "cancelled",
            "cancelled": True,
            "cancel_requested": True,
            "method": "jobs_cancel",
            "previous_status": before_status,
            "state": before,
        })

    after = prompt_status(backend, prompt_id)
    after_status = str(after.get("status") or "running")
    final_cancelled = after_status == "cancelled"
    return finish({
        "ok": True,
        "task_id": prompt_id,
        "status": "cancelled" if final_cancelled else "cancel_requested",
        "backend_status": after_status,
        "cancelled": final_cancelled,
        "cancel_requested": True,
        "method": "jobs_cancel",
        "previous_status": before_status,
        "state": after,
    })
