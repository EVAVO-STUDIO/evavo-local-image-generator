#!/usr/bin/env python3
"""Gateway provider adapter for local Kokoro-FastAPI.

This is deliberately narrow: Kokoro is a high-quality speech provider, not a
replacement for EVAVO Audio Studio's broader music/SFX/mastering workflows.
START-GATEWAY.ps1 only selects this adapter when Audio Studio is unavailable
and the local Kokoro API has already proven healthy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from evavo_local_image_generator.backends import KokoroBackend


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_request(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read request JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("request JSON root must be an object")
    return value


def _nested(request: dict[str, Any], name: str, default: Any = None) -> Any:
    if name in request:
        return request[name]
    options = request.get("options")
    if isinstance(options, dict) and name in options:
        return options[name]
    return default


def _speech_text(request: dict[str, Any]) -> str:
    for key in ("text", "input", "prompt"):
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("Kokoro speech request requires non-empty text/input/prompt")


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAVO gateway adapter for local Kokoro-FastAPI")
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--endpoint", default=os.getenv("KOKORO_ENDPOINT") or os.getenv("EVAVO_KOKORO_ENDPOINT") or "http://127.0.0.1:8880")
    args = parser.parse_args()

    try:
        request_path = Path(args.request_json).expanduser().resolve(strict=True)
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        request = _read_request(request_path)
        text = _speech_text(request)

        voice = str(_nested(request, "voice", os.getenv("EVAVO_KOKORO_VOICE") or "af_heart"))
        speed = float(_nested(request, "speed", 1.0))

        # WAV is the production-quality default. Callers can explicitly request
        # another Kokoro-supported format, but compressed delivery should happen
        # downstream whenever possible so the gateway retains a lossless master.
        response_format = str(
            _nested(request, "response_format", _nested(request, "format", "wav"))
        ).strip().lower()
        if response_format not in {"wav", "flac", "mp3", "opus", "aac", "pcm"}:
            raise ValueError("unsupported Kokoro response_format")

        suffix = {
            "wav": ".wav",
            "flac": ".flac",
            "mp3": ".mp3",
            "opus": ".opus",
            "aac": ".aac",
            "pcm": ".pcm",
        }[response_format]
        target = output_dir / f"{args.task_id}-kokoro{suffix}"

        backend = KokoroBackend(args.endpoint)
        health = backend.health()
        if not health.get("healthy"):
            raise RuntimeError("Kokoro health check did not report ready")
        generated = backend.synthesize(
            text,
            target,
            voice=voice,
            speed=speed,
            response_format=response_format,
            validate_voice=True,
        )

        receipt = {
            "ok": True,
            "provider": "kokoro-fastapi",
            "backendMode": "local-kokoro-fastapi",
            "taskId": args.task_id,
            "output": str(target.resolve()),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "voice": generated.get("voice"),
            "speed": generated.get("speed"),
            "format": generated.get("response_format"),
            "endpoint": generated.get("endpoint"),
        }
        print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        # ProviderRouter reads the final JSON object and requires ok=true. Keep
        # the failure bounded and machine-readable without leaking stack traces.
        print(
            json.dumps(
                {
                    "ok": False,
                    "provider": "kokoro-fastapi",
                    "taskId": args.task_id,
                    "error": str(exc)[:2000],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
