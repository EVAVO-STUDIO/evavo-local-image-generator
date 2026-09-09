#!/usr/bin/env python3
"""Shared operational primitives for the EVAVO local image generator.

This module intentionally uses only the Python standard library so the
operational utilities can run immediately after a normal Python install.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ROOT = Path(__file__).resolve().parent
DEFAULT_ENDPOINT = os.environ.get("COMFYUI_ENDPOINT", "http://127.0.0.1:8188").rstrip("/")
SERVICE_NAME = "evavo-local-image-generator"
PROTOCOL_VERSION = 1
HISTORY_FILE = Path(os.environ.get("EVAVO_TASK_HISTORY", str(ROOT / "task_history.json"))).expanduser().resolve()
VALID_STATUSES = {"queued", "running", "completed", "failed", "cancelled", "unknown"}
TASK_STRING_FIELDS = {
    "error_code",
    "error_message",
    "output_uri",
    "backend_mode",
    "checkpoint",
    "workflow_path",
    "output_dir",
    "cancel_requested_at",
    "cancelled_at",
    "cancel_method",
    "backend_status",
}


def now_iso() -> str:
    """Return a timezone-aware local ISO-8601 timestamp."""
    return datetime.now().astimezone().isoformat()


def normalize_status(status: str) -> str:
    value = str(status or "unknown").strip().lower()
    return value if value in VALID_STATUSES else "unknown"


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Perform an HTTP request and require a JSON object response."""
    body = None
    headers = {"Accept": "application/json", "User-Agent": "EVAVO-Operations/1"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP_ERROR:{exc.code}:{detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"CONNECTION_ERROR:{reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("TIMEOUT:request timed out") from exc
    except OSError as exc:
        raise RuntimeError(f"CONNECTION_ERROR:{exc}") from exc

    if not 200 <= int(status) < 300:
        raise RuntimeError(f"HTTP_ERROR:{status}:unexpected response status")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("INVALID_JSON:service did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("INVALID_RESPONSE:expected a JSON object")
    return parsed


def validate_health(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the EVAVO health identity/protocol contract."""
    if payload.get("service") != SERVICE_NAME:
        raise RuntimeError("WRONG_SERVICE:port 8188 is not the EVAVO service")
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("PROTOCOL_MISMATCH:unsupported EVAVO service protocol")
    if payload.get("status") not in {"ready", "ok"}:
        raise RuntimeError(f"NOT_READY:{payload.get('status', 'unknown')}")
    return payload


def _windows_mutex_name(lock_path: Path) -> str:
    """Derive a short, non-secret per-lock Windows named-mutex identity."""
    normalized = os.path.normcase(os.path.abspath(str(lock_path))).replace("/", "\\")
    digest = hashlib.sha256(normalized.encode("utf-8", errors="surrogatepass")).hexdigest()
    return f"Local\\EVAVO-{digest}"


def _remaining_milliseconds(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 0
    return max(1, min(0xFFFFFFFE, int(remaining * 1000)))


@contextmanager
def _windows_interprocess_lock(lock_path: Path, timeout: float) -> Iterator[None]:
    """Use a Windows named mutex and interoperate safely with legacy .lock files."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    WAIT_OBJECT_0 = 0x00000000
    WAIT_ABANDONED = 0x00000080
    WAIT_TIMEOUT = 0x00000102
    deadline = time.monotonic() + max(0.0, float(timeout))
    handle = kernel32.CreateMutexW(None, False, _windows_mutex_name(lock_path))
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")

    legacy_handle = None
    mutex_acquired = False
    legacy_locked = False
    try:
        status = kernel32.WaitForSingleObject(handle, _remaining_milliseconds(deadline))
        if status == WAIT_TIMEOUT:
            raise TimeoutError(f"Timed out acquiring EVAVO interprocess lock: {lock_path}")
        if status not in {WAIT_OBJECT_0, WAIT_ABANDONED}:
            raise OSError(f"WaitForSingleObject failed with status 0x{status:08x}")
        mutex_acquired = True

        if lock_path.exists():
            try:
                legacy_handle = open(lock_path, "r+b")
            except OSError:
                legacy_handle = None
            if legacy_handle is not None:
                while True:
                    try:
                        legacy_handle.seek(0)
                        if legacy_handle.read(1) == b"":
                            legacy_handle.seek(0)
                            legacy_handle.write(b"0")
                            legacy_handle.flush()
                        legacy_handle.seek(0)
                        msvcrt.locking(legacy_handle.fileno(), msvcrt.LK_NBLCK, 1)
                        legacy_locked = True
                        break
                    except (OSError, BlockingIOError):
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"Timed out acquiring legacy EVAVO interprocess lock: {lock_path}")
                        time.sleep(0.05)

        yield
    finally:
        if legacy_handle is not None:
            try:
                if legacy_locked:
                    legacy_handle.seek(0)
                    msvcrt.locking(legacy_handle.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                legacy_handle.close()
            try:
                lock_path.unlink()
            except OSError:
                pass
        if mutex_acquired:
            kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


@contextmanager
def interprocess_lock(lock_path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Acquire a tiny cross-platform interprocess lock using only stdlib APIs.

    Windows uses a named mutex, eliminating persistent ``*.lock`` artifacts that
    some agent environments mistakenly treat as active blockers. During migration,
    an already-existing legacy lock file is also honored so older EVAVO processes
    cannot race newer ones. POSIX retains advisory ``flock`` semantics.
    """
    lock_path = Path(lock_path)
    if os.name == "nt":
        with _windows_interprocess_lock(lock_path, timeout):
            yield
        return

    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (OSError, BlockingIOError):
            if time.monotonic() >= deadline:
                handle.close()
                raise TimeoutError(f"Timed out acquiring EVAVO interprocess lock: {lock_path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


_interprocess_lock = interprocess_lock


def _clean_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item)]


class TaskTracker:
    """Atomic, lock-protected JSON task history used by CLI and MCP tools."""

    def __init__(self, history_file: Path | str = HISTORY_FILE):
        self.history_file = Path(history_file).expanduser().resolve()
        self.lock_file = self.history_file.with_suffix(self.history_file.suffix + ".lock")
        self.tasks: List[Dict[str, Any]] = []
        self.load_history()

    def _read_unlocked(self) -> List[Dict[str, Any]]:
        if not self.history_file.exists():
            return []
        try:
            with self.history_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CORRUPT_HISTORY:{self.history_file}:{exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"HISTORY_READ_ERROR:{self.history_file}:{exc}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"CORRUPT_HISTORY:{self.history_file}:root must be a JSON array")
        return [item for item in data if isinstance(item, dict)]

    def _write_unlocked(self, tasks: List[Dict[str, Any]]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=self.history_file.name + ".",
            suffix=".tmp",
            dir=str(self.history_file.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(tasks, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.history_file)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def load_history(self) -> List[Dict[str, Any]]:
        with interprocess_lock(self.lock_file):
            self.tasks = self._read_unlocked()
        return list(self.tasks)

    def add_task(
        self,
        task_id: str,
        prompt: str,
        status: str = "queued",
        *,
        project_name: str = "batch_gen",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        backend_mode: Optional[str] = None,
        checkpoint: Optional[str] = None,
        workflow_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_uris: Optional[List[str]] = None,
        cancel_requested_at: Optional[str] = None,
        cancelled_at: Optional[str] = None,
        cancel_method: Optional[str] = None,
        backend_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        timestamp = now_iso()
        record: Dict[str, Any] = {
            "task_id": task_id.strip(),
            "prompt": str(prompt),
            "project_name": str(project_name),
            "status": normalize_status(status),
            "timestamp": timestamp,
            "updated": timestamp,
        }
        optional_strings = {
            "error_code": error_code,
            "error_message": error_message,
            "backend_mode": backend_mode,
            "checkpoint": checkpoint,
            "workflow_path": workflow_path,
            "output_dir": output_dir,
            "cancel_requested_at": cancel_requested_at,
            "cancelled_at": cancelled_at,
            "cancel_method": cancel_method,
            "backend_status": backend_status,
        }
        for key, value in optional_strings.items():
            if value is not None and str(value):
                record[key] = str(value)
        cleaned_outputs = _clean_string_list(output_uris)
        if cleaned_outputs:
            record["output_uris"] = cleaned_outputs
            record["output_uri"] = cleaned_outputs[0]

        with interprocess_lock(self.lock_file):
            tasks = self._read_unlocked()
            existing = next((item for item in tasks if item.get("task_id") == record["task_id"]), None)
            if existing is None:
                tasks.append(record)
            else:
                existing.update(record)
                record = existing
            self._write_unlocked(tasks)
            self.tasks = tasks
        return dict(record)

    def update_task(self, task_id: str, status: str, **fields: Any) -> Dict[str, Any]:
        with interprocess_lock(self.lock_file):
            tasks = self._read_unlocked()
            target = next((item for item in tasks if item.get("task_id") == task_id), None)
            if target is None:
                raise KeyError(task_id)
            target["status"] = normalize_status(status)
            target["updated"] = now_iso()

            for key in TASK_STRING_FIELDS:
                if key in fields and fields[key] is not None:
                    target[key] = str(fields[key])

            if "output_uris" in fields and fields["output_uris"] is not None:
                cleaned_outputs = _clean_string_list(fields["output_uris"])
                target["output_uris"] = cleaned_outputs
                if cleaned_outputs:
                    target["output_uri"] = cleaned_outputs[0]

            self._write_unlocked(tasks)
            self.tasks = tasks
            return dict(target)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        self.load_history()
        target = next((item for item in self.tasks if item.get("task_id") == task_id), None)
        return dict(target) if target is not None else None

    def list_tasks(self, limit: int = 20, project: Optional[str] = None) -> List[Dict[str, Any]]:
        self.load_history()
        tasks = self.tasks
        if project:
            tasks = [task for task in tasks if task.get("project_name") == project]
        if limit < 1:
            return []
        return [dict(item) for item in tasks[-limit:]]

    def get_statistics(self) -> Dict[str, int]:
        self.load_history()
        stats = {status: 0 for status in sorted(VALID_STATUSES)}
        for task in self.tasks:
            stats[normalize_status(task.get("status", "unknown"))] += 1
        return {"total_tasks": len(self.tasks), **stats}

    def clear_history(self) -> None:
        with interprocess_lock(self.lock_file):
            self._write_unlocked([])
            self.tasks = []
