"""Normalize native ComfyUI prompt/job state for EVAVO agents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .backends import ComfyUIBackend

_JOB_STATUS_MAP = {
    "waiting_to_dispatch": "queued",
    "pending": "queued",
    "queued": "queued",
    "in_progress": "running",
    "running": "running",
    "completed": "completed",
    "success": "completed",
    "error": "failed",
    "failed": "failed",
    "failure": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def _outputs_from_history(history: Dict[str, Any], prompt_id: str) -> List[Dict[str, str]]:
    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        return []
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return []
    found: List[Dict[str, str]] = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images")
        if not isinstance(images, list):
            continue
        for image in images:
            if not isinstance(image, dict) or not isinstance(image.get("filename"), str):
                continue
            found.append(
                {
                    "filename": image["filename"],
                    "subfolder": str(image.get("subfolder", "")),
                    "type": str(image.get("type", "output")),
                }
            )
    return found


def _queue_contains(items: Any, prompt_id: str) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if isinstance(item, dict):
            if item.get("prompt_id") == prompt_id or item.get("id") == prompt_id:
                return True
            continue
        if isinstance(item, (list, tuple)) and len(item) > 1 and item[1] == prompt_id:
            return True
    return False


def _current_job(backend: ComfyUIBackend, prompt_id: str) -> Optional[Dict[str, Any]]:
    try:
        payload = backend.job_detail(prompt_id)
    except RuntimeError as exc:
        if str(exc).startswith("COMFYUI_HTTP_ERROR:404:"):
            return None
        raise
    return payload if isinstance(payload, dict) else None


def _history_state(backend: ComfyUIBackend, prompt_id: str) -> Optional[Dict[str, Any]]:
    history = backend.history(prompt_id)
    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        return None
    outputs = _outputs_from_history(history, prompt_id)
    raw_status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    status_str = str(raw_status.get("status_str", "")).strip().lower()
    completed = raw_status.get("completed")
    messages = raw_status.get("messages") if isinstance(raw_status.get("messages"), list) else []
    if status_str in {"cancelled", "canceled", "interrupted"}:
        status = "cancelled"
    else:
        failed = status_str in {"error", "failed", "failure"}
        if not failed and completed is False:
            failed = any(
                isinstance(message, (list, tuple))
                and message
                and str(message[0]).strip().lower() in {"execution_error", "error", "failed", "failure"}
                for message in messages
            )
        if failed:
            status = "failed"
        elif outputs or completed is True or status_str in {"success", "completed"}:
            status = "completed"
        elif status_str in {"running", "executing"}:
            status = "running"
        else:
            status = "unknown"
    return {
        "task_id": prompt_id,
        "status": status,
        "outputs": outputs,
        "history_present": True,
        "job_api": False,
        "comfyui_status": status_str or None,
        "completed": completed,
        "messages": messages,
        "error_message": None,
    }


def prompt_status(backend: ComfyUIBackend, prompt_id: str) -> Dict[str, Any]:
    """Return normalized queued/running/completed/failed/cancelled/unknown state."""
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError("prompt_id must be a non-empty string")
    prompt_id = prompt_id.strip()
    job = _current_job(backend, prompt_id)
    if job is not None:
        raw = str(job.get("status", "")).strip().lower()
        normalized = _JOB_STATUS_MAP.get(raw, "unknown")
        history_state: Optional[Dict[str, Any]] = None
        if normalized in {"completed", "failed"}:
            try:
                history_state = _history_state(backend, prompt_id)
            except RuntimeError:
                history_state = None
        outputs = history_state.get("outputs", []) if history_state else []
        messages = history_state.get("messages", []) if history_state else []
        error_message = job.get("error_message")
        if normalized == "failed" and not messages and error_message:
            messages = [["job_error", {"exception_message": str(error_message)}]]
        return {
            "task_id": prompt_id,
            "status": normalized,
            "outputs": outputs,
            "history_present": history_state is not None,
            "job_api": True,
            "comfyui_status": raw or None,
            "completed": normalized in {"completed", "failed", "cancelled"},
            "messages": messages,
            "error_message": str(error_message) if error_message not in {None, ""} else None,
        }
    legacy = _history_state(backend, prompt_id)
    if legacy is not None:
        return legacy
    queue = backend.queue_state()
    running = queue.get("queue_running")
    pending = queue.get("queue_pending")
    if _queue_contains(running, prompt_id):
        status = "running"
    elif _queue_contains(pending, prompt_id):
        status = "queued"
    else:
        status = "unknown"
    return {
        "task_id": prompt_id,
        "status": status,
        "outputs": [],
        "history_present": False,
        "job_api": False,
        "comfyui_status": None,
        "completed": None,
        "messages": [],
        "error_message": None,
    }
