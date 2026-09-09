#!/usr/bin/env python3
"""Safely reconcile and optionally resume an EVAVO batch manifest.

Default behavior is non-duplicating: known backend task IDs are queried, never
resubmitted. Retrying failed or pending work requires explicit flags. A failed
item that already owns a non-local task ID requires an additional force flag
because the backend may have accepted work before the original wrapper failed.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from evavo_operations import TaskTracker, now_iso
from evavo_local_image_generator.prompt_quality import lint_prompt

ROOT = Path(__file__).resolve().parent
WRAPPER = ROOT / "evavo-wrapper.py"


def _batch_module():
    path = ROOT / "generate-batch.py"
    spec = importlib.util.spec_from_file_location("evavo_batch_resume_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generate-batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _load_manifest(path_value: str | Path) -> tuple[Path, Dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read batch manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("items"), list):
        raise ValueError("unsupported or malformed batch manifest")
    return path, payload


def _known_backend_task(task_id: Any) -> bool:
    return isinstance(task_id, str) and bool(task_id) and not task_id.startswith("local_failed_")


def _run_wrapper(command: str, payload: Dict[str, Any], endpoint: str, timeout: float) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, str(WRAPPER), command, json.dumps(payload, ensure_ascii=False), "--endpoint", endpoint],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "status": "unknown", "error_code": "RECONCILE_PROCESS_ERROR", "message": str(exc)}
    stdout = result.stdout.strip()
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": "unknown",
            "error_code": "RECONCILE_INVALID_JSON",
            "message": (stdout or result.stderr.strip() or "wrapper returned no JSON")[:1000],
        }
    if not isinstance(value, dict):
        return {"ok": False, "status": "unknown", "error_code": "RECONCILE_INVALID_RESPONSE", "message": "wrapper response was not an object"}
    return value


class ResumeManifestStore:
    def __init__(self, path: Path, payload: Dict[str, Any]):
        self.path = path
        self.payload = payload
        self._lock = asyncio.Lock()

    async def record(self, index: int, result: Dict[str, Any]) -> None:
        async with self._lock:
            item = self.payload["items"][index]
            item["status"] = str(result.get("status", "unknown"))
            item["task_id"] = result.get("task_id")
            item["result"] = result
            item["updated_at"] = now_iso()
            await asyncio.to_thread(_write_json_atomic, self.path, self.payload)

    async def note(self, entry: Dict[str, Any]) -> None:
        async with self._lock:
            history = self.payload.setdefault("resume_history", [])
            if not isinstance(history, list):
                history = []
                self.payload["resume_history"] = history
            history.append(entry)
            await asyncio.to_thread(_write_json_atomic, self.path, self.payload)

    async def finish(self) -> None:
        async with self._lock:
            statuses = [str(item.get("status", "unknown")) for item in self.payload["items"] if isinstance(item, dict)]
            self.payload["last_reconciled_at"] = now_iso()
            self.payload["summary"] = {
                "ok": bool(statuses) and all(status in {"queued", "completed"} for status in statuses),
                "accepted": sum(status in {"queued", "completed"} for status in statuses),
                "queued": statuses.count("queued"),
                "completed": statuses.count("completed"),
                "failed": statuses.count("failed"),
                "pending": statuses.count("pending"),
                "unknown": statuses.count("unknown"),
                "total": len(statuses),
            }
            await asyncio.to_thread(_write_json_atomic, self.path, self.payload)


def _persist_one(batch: Any, result: Dict[str, Any]) -> None:
    tracker = TaskTracker()
    downloaded = result.get("downloaded_files")
    output_uris = [str(item) for item in downloaded] if isinstance(downloaded, list) else None
    tracker.add_task(
        str(result["task_id"]),
        str(result.get("prompt", "")),
        str(result.get("status", "unknown")),
        project_name=str(result.get("project_name", "batch_gen")),
        error_code=result.get("error_code"),
        error_message=result.get("message"),
        backend_mode=result.get("backend_mode"),
        checkpoint=result.get("checkpoint"),
        workflow_path=result.get("workflow_path"),
        output_dir=result.get("output_dir"),
        output_uris=output_uris,
        generation_receipt=batch._receipt(result),
    )


async def run(args: argparse.Namespace) -> int:
    batch = _batch_module()
    path, manifest = _load_manifest(args.manifest)
    endpoint = str(args.endpoint or manifest.get("endpoint") or "").rstrip("/")
    if not endpoint:
        raise ValueError("batch manifest has no endpoint; provide --endpoint")
    project = str(manifest.get("project_name") or "batch_gen")
    workflow_path = manifest.get("workflow_path") if isinstance(manifest.get("workflow_path"), str) else None
    wait = bool(manifest.get("wait"))
    wait_timeout = float(manifest.get("wait_timeout") or 600.0)
    output_dir = args.output_dir
    store = ResumeManifestStore(path, manifest)

    try:
        health = await batch.preflight(endpoint)
    except RuntimeError as exc:
        await store.note({"at": now_iso(), "action": "preflight", "ok": False, "error": str(exc)})
        print(json.dumps({"ok": False, "error": f"backend preflight failed: {exc}", "manifest": str(path)}, indent=2))
        return 3
    await store.note({"at": now_iso(), "action": "preflight", "ok": True, "health": health})

    reconciled = 0
    retained = 0
    retry_candidates: list[tuple[int, Dict[str, Any], Dict[str, Any]]] = []

    for index, item in enumerate(manifest["items"]):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "pending"))
        task_id = item.get("task_id")
        prompt = str(item.get("prompt", ""))
        options = dict(item.get("generation_options")) if isinstance(item.get("generation_options"), dict) else {}
        lint = lint_prompt(prompt, str(options.get("negative_prompt", "")))
        recorded_sha = item.get("prompt_sha256")
        if recorded_sha and recorded_sha != lint["prompt_sha256"]:
            item["status"] = "failed"
            item["result"] = {
                "status": "failed",
                "task_id": task_id,
                "prompt": prompt,
                "project_name": project,
                "error_code": "RESUME_PROMPT_FINGERPRINT_MISMATCH",
                "message": "stored prompt/negative pair no longer matches the manifest fingerprint",
                "prompt_quality": lint,
            }
            continue

        if status == "completed":
            retained += 1
            continue

        if _known_backend_task(task_id):
            payload: Dict[str, Any] = {"task_id": task_id}
            if output_dir:
                payload.update({"download": True, "output_dir": output_dir})
            current = await asyncio.to_thread(_run_wrapper, "task_status", payload, endpoint, args.reconcile_timeout)
            current_status = str(current.get("status", "unknown"))
            current.update({"prompt": prompt, "project_name": project, "prompt_quality": lint})
            if workflow_path:
                current["workflow_path"] = workflow_path
            if current_status in {"completed", "queued"}:
                await store.record(index, current)
                reconciled += 1
                try:
                    _persist_one(batch, current)
                except Exception:
                    pass
                continue
            # A known backend task is never silently duplicated. Retrying it is
            # only admitted with the explicit identified-failure force switch.
            if status == "failed" and args.retry_failed and args.force_retry_identified:
                retry_candidates.append((index, item, lint))
            else:
                item["reconciliation"] = current
                item["updated_at"] = now_iso()
                retained += 1
            continue

        if status == "failed" and args.retry_failed:
            retry_candidates.append((index, item, lint))
        elif status in {"pending", "unknown"} and args.retry_pending:
            retry_candidates.append((index, item, lint))
        else:
            retained += 1

    if retry_candidates:
        semaphore = asyncio.Semaphore(max(1, min(args.concurrency, 8)))
        tasks = []
        for index, item, lint in retry_candidates:
            prompt = str(item.get("prompt", ""))
            options = dict(item.get("generation_options")) if isinstance(item.get("generation_options"), dict) else {}
            item["retry_count"] = int(item.get("retry_count", 0) or 0) + 1
            item["retry_started_at"] = now_iso()
            tasks.append(
                batch.queue_generation(
                    prompt,
                    project,
                    endpoint,
                    semaphore,
                    args.queue_timeout,
                    wait=wait,
                    wait_timeout=wait_timeout,
                    output_dir=output_dir,
                    workflow_path=workflow_path,
                    workflow_preflight_already_done=False,
                    generation_options=options,
                    prompt_quality=lint,
                    manifest_index=index,
                    run_store=store,
                )
            )
        results = await asyncio.gather(*tasks)
        for result in results:
            try:
                _persist_one(batch, result)
            except Exception:
                pass

    await store.note(
        {
            "at": now_iso(),
            "action": "resume",
            "reconciled": reconciled,
            "retained_without_resubmit": retained,
            "retried": len(retry_candidates),
            "retry_failed": bool(args.retry_failed),
            "retry_pending": bool(args.retry_pending),
            "force_retry_identified": bool(args.force_retry_identified),
        }
    )
    await store.finish()
    summary = manifest.get("summary", {})
    result = {
        "ok": bool(summary.get("ok")),
        "manifest": str(path),
        "reconciled": reconciled,
        "retained_without_resubmit": retained,
        "retried": len(retry_candidates),
        "summary": summary,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile and safely resume an EVAVO batch manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--endpoint", default="", help="Override the endpoint recorded in the manifest")
    parser.add_argument("--output-dir", default="", help="Download completed reconciled/retried outputs here")
    parser.add_argument("--retry-failed", action="store_true", help="Retry failed items that have no known backend task ID")
    parser.add_argument("--retry-pending", action="store_true", help="Explicitly retry pending/unknown items; may duplicate work if the prior process died before recording a task ID")
    parser.add_argument("--force-retry-identified", action="store_true", help="Allow retry of a failed item even when it already has a backend task ID")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--queue-timeout", type=float, default=30.0)
    parser.add_argument("--reconcile-timeout", type=float, default=15.0)
    args = parser.parse_args()
    if args.concurrency < 1 or args.concurrency > 8:
        parser.error("--concurrency must be between 1 and 8 for recovery")
    if args.queue_timeout <= 0 or args.reconcile_timeout <= 0:
        parser.error("timeouts must be greater than zero")
    try:
        return asyncio.run(run(args))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
