#!/usr/bin/env python3
"""End-to-end smoke test for the fixed EVAVO Gateway HTTP contract."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

TASK_RE = re.compile(r"^img_\d+$")


def request(url: str, *, method: str = "GET", payload: Dict[str, Any] | None = None, timeout: float = 10.0) -> Tuple[int, bytes, Dict[str, str], float]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "EVAVO-Gateway-Smoke/1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            status = int(getattr(response, "status", 200))
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        data = exc.read()
        status = exc.code
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
    elapsed = (time.perf_counter() - started) * 1000
    return status, data, response_headers, elapsed


def json_request(url: str, **kwargs: Any) -> Tuple[int, Dict[str, Any], float]:
    status, data, _, elapsed = request(url, **kwargs)
    payload = json.loads(data.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return status, payload, elapsed


async def websocket_probe(base: str, task_id: str) -> Dict[str, Any]:
    try:
        import websockets
    except ImportError:
        return {"ok": False, "skipped": True, "reason": "websockets package unavailable"}
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/progress/{task_id}"
    started = time.perf_counter()
    try:
        async with websockets.connect(ws_url, open_timeout=5) as socket:
            raw = await asyncio.wait_for(socket.recv(), timeout=5)
            payload = json.loads(raw)
            return {"ok": isinstance(payload, dict) and payload.get("task_id") == task_id, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "event": payload}
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test EVAVO Unified Gateway")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt", default="EVAVO gateway verification: a beautiful sunset over mountains")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", default="evavo-state/smoke-test-result.png")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    report: Dict[str, Any] = {"base": base, "started_at": time.time(), "checks": {}}

    try:
        status, health, latency = json_request(base + "/health")
        expected = {"status": "healthy", "gateway": "ok", "comfyui": "ok"}
        report["checks"]["health"] = {"ok": status == 200 and health == expected, "status_code": status, "latency_ms": round(latency, 1), "response": health}

        status, openapi, latency = json_request(base + "/openapi.json")
        required = {"/health", "/generate/image", "/tasks", "/tasks/{task_id}/status", "/results/{task_id}"}
        paths = set(openapi.get("paths", {}).keys()) if isinstance(openapi.get("paths"), dict) else set()
        report["checks"]["openapi"] = {"ok": status == 200 and required.issubset(paths), "latency_ms": round(latency, 1), "missing_paths": sorted(required - paths)}

        status, queued, latency = json_request(base + "/generate/image", method="POST", payload={"prompt": args.prompt})
        task_id = str(queued.get("task_id", ""))
        queue_ok = status == 202 and TASK_RE.fullmatch(task_id) is not None and queued.get("status") == "queued" and queued.get("progress") == 0
        report["checks"]["queue"] = {"ok": queue_ok, "status_code": status, "latency_ms": round(latency, 1), "response": queued}
        if not queue_ok:
            raise RuntimeError("Image queue contract failed")

        report["checks"]["websocket"] = asyncio.run(websocket_probe(base, task_id))

        deadline = time.monotonic() + args.timeout
        polls = 0
        latest: Dict[str, Any] = {}
        poll_latencies = []
        while time.monotonic() < deadline:
            polls += 1
            status, latest, latency = json_request(base + f"/tasks/{task_id}/status")
            poll_latencies.append(latency)
            if latest.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.5)
        report["checks"]["task_tracking"] = {
            "ok": latest.get("status") == "completed" and latest.get("progress") == 100,
            "polls": polls,
            "average_poll_latency_ms": round(sum(poll_latencies) / max(1, len(poll_latencies)), 1),
            "final": latest,
        }
        if latest.get("status") != "completed":
            raise RuntimeError(f"Generation did not complete successfully: {latest}")

        status, data, headers, latency = request(base + f"/results/{task_id}", timeout=30.0)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        report["checks"]["result"] = {
            "ok": status == 200 and len(data) > 0,
            "status_code": status,
            "latency_ms": round(latency, 1),
            "bytes": len(data),
            "content_type": headers.get("content-type"),
            "output": str(output),
        }
    except Exception as exc:
        report["error"] = str(exc)

    checks = report.get("checks", {})
    report["ok"] = bool(checks) and all(bool(item.get("ok")) or bool(item.get("skipped")) for item in checks.values() if isinstance(item, dict)) and "error" not in report
    report["finished_at"] = time.time()
    report["duration_ms"] = round((report["finished_at"] - report["started_at"]) * 1000, 1)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
