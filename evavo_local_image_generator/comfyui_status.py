"""Normalize native ComfyUI prompt history/queue state for EVAVO agents."""

from __future__ import annotations

from typing import Any, Dict, List

from .backends import ComfyUIBackend


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


def prompt_status(backend: ComfyUIBackend, prompt_id: str) -> Dict[str, Any]:
    """Return one normalized prompt state using `/history` then `/queue`.

    ComfyUI history is authoritative for terminal execution. If no history entry
    exists yet, queue state distinguishes actively running from pending work.
    """
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ValueError("prompt_id must be a non-empty string")
    prompt_id = prompt_id.strip()

    history = backend.history(prompt_id)
    entry = history.get(prompt_id)
    if isinstance(entry, dict):
        outputs = _outputs_from_history(history, prompt_id)
        raw_status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
        status_str = str(raw_status.get("status_str", "")).strip().lower()
        completed = raw_status.get("completed")
        messages = raw_status.get("messages") if isinstance(raw_status.get("messages"), list) else []

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
            "comfyui_status": status_str or None,
            "completed": completed,
            "messages": messages,
        }

    queue = backend._request("/queue", timeout=10.0)
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
        "comfyui_status": None,
        "completed": None,
        "messages": [],
    }
